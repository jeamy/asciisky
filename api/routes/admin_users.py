from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from db_utils import get_db_connection, db_transaction
from api.routes.auth import _hash_password


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _require_admin(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not request.session.get("user_is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid session")


class AdminUserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    is_admin: bool = False
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


def _row_to_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"],
        "is_active": row["is_active"],
        "is_admin": row["is_admin"],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("")
async def list_users(
    request: Request,
    q: Optional[str] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, List[Dict[str, Any]]]:
    _require_admin(request)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = (
            "SELECT id, email, username, is_active, is_admin, created_at, updated_at "
            "FROM users"
        )
        conditions: List[str] = []
        params: List[Any] = []

        if active_only:
            conditions.append("is_active = TRUE")

        if q:
            conditions.append("(email ILIKE %s OR username ILIKE %s)")
            like_q = f"%{q}%"
            params.extend([like_q, like_q])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY id ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        users = [_row_to_user(row) for row in rows]
        return {"users": users}
    finally:
        conn.close()


@router.post("")
async def create_user(payload: AdminUserCreate, request: Request) -> Dict[str, Dict[str, Any]]:
    _require_admin(request)

    email = payload.email.strip().lower()
    username = payload.username.strip()
    password = payload.password

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    password_hash = _hash_password(password)
    now = datetime.utcnow()

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE email = %s OR username = %s LIMIT 1",
            (email, username),
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail="User with same email or username already exists",
            )

        cursor.execute(
            """
            INSERT INTO users (email, username, password_hash, is_active, is_admin, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, username, is_active, is_admin, created_at, updated_at
            """,
            (email, username, password_hash, payload.is_active, payload.is_admin, now, now),
        )
        row = cursor.fetchone()

    return {"user": _row_to_user(row)}


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
) -> Dict[str, Dict[str, Any]]:
    _require_admin(request)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    with db_transaction() as conn:
        cursor = conn.cursor()

        new_email = data.get("email")
        new_username = data.get("username")

        if new_email or new_username:
            conditions: List[str] = []
            params: List[Any] = []
            if new_email:
                conditions.append("email = %s")
                params.append(new_email.strip().lower())
            if new_username:
                conditions.append("username = %s")
                params.append(new_username.strip())

            sql = (
                "SELECT id FROM users WHERE (" + " OR ".join(conditions) + ") "
                "AND id <> %s LIMIT 1"
            )
            params.append(user_id)
            cursor.execute(sql, tuple(params))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="Another user with same email or username already exists",
                )

        fields: List[str] = []
        params2: List[Any] = []

        if new_email:
            fields.append("email = %s")
            params2.append(new_email.strip().lower())
        if new_username:
            fields.append("username = %s")
            params2.append(new_username.strip())
        if "password" in data and data["password"] is not None:
            if len(data["password"]) < 6:
                raise HTTPException(status_code=400, detail="Password too short")
            fields.append("password_hash = %s")
            params2.append(_hash_password(data["password"]))
        if "is_admin" in data and data["is_admin"] is not None:
            fields.append("is_admin = %s")
            params2.append(bool(data["is_admin"]))
        if "is_active" in data and data["is_active"] is not None:
            fields.append("is_active = %s")
            params2.append(bool(data["is_active"]))

        fields.append("updated_at = %s")
        params2.append(datetime.utcnow())
        params2.append(user_id)

        cursor.execute(
            """
            UPDATE users
            SET """
            + ", ".join(fields)
            + " WHERE id = %s "
            "RETURNING id, email, username, is_active, is_admin, created_at, updated_at",
            tuple(params2),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

    return {"user": _row_to_user(row)}


@router.delete("/{user_id}")
async def delete_user(user_id: int, request: Request) -> Dict[str, Any]:
    """Permanently delete a user from the database.

    This performs a hard delete from the users table. Related rows in
    user_settings are removed automatically via ON DELETE CASCADE.
    """
    _require_admin(request)

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM users
            WHERE id = %s
            RETURNING id
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

    return {"deleted": True, "id": row["id"]}
