import hashlib
import hmac
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from db_utils import db_transaction, get_db_connection

router = APIRouter()


# ===== Password hashing (PBKDF2-HMAC-SHA256) =====

_ALG = "pbkdf2_sha256"
_ITERATIONS = 390000
_SALT_BYTES = 16


def _hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be non-empty string")
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALG}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        alg, iterations_str, salt_hex, hash_hex = stored.split("$")
        if alg != _ALG:
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ===== Pydantic models =====


class RegisterPayload(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginPayload(BaseModel):
    identifier: str  # username OR email
    password: str


class AuthUser(BaseModel):
    id: int
    email: EmailStr
    username: str
    is_admin: bool
    is_active: bool


# ===== Helpers =====


def _get_user_by_identifier(identifier: str) -> dict | None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, username, password_hash, is_active, is_admin
            FROM users
            WHERE username = %s OR email = %s
            LIMIT 1
            """,
            (identifier, identifier),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_user_by_id(user_id: int) -> dict | None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, username, is_active, is_admin
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _session_set_user(request: Request, user: dict) -> None:
    request.session["user_id"] = int(user["id"])
    request.session["user_email"] = user["email"]
    request.session["user_name"] = user["username"]
    request.session["user_is_admin"] = bool(user.get("is_admin"))


def _session_clear_user(request: Request) -> None:
    for key in ("user_id", "user_email", "user_name", "user_is_admin"):
        try:
            request.session.pop(key, None)
        except Exception:
            pass


# ===== Routes =====


@router.post("/auth/register")
async def register(payload: RegisterPayload, request: Request):
    email = payload.email.strip().lower()
    username = payload.username.strip()
    password = payload.password

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short")

    password_hash = _hash_password(password)

    with db_transaction() as conn:
        cursor = conn.cursor()
        # Serialize the bootstrap decision.  Without this lock, two first
        # registrations can both observe an empty users table and become admin.
        cursor.execute("LOCK TABLE users IN EXCLUSIVE MODE")
        # Check duplicates
        cursor.execute(
            "SELECT id FROM users WHERE email = %s OR username = %s LIMIT 1",
            (email, username),
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="User with same email or username already exists")

        # First user becomes admin automatically, others are normal users
        cursor.execute("SELECT COUNT(*) AS count FROM users")
        count_row = cursor.fetchone()
        existing_count = count_row["count"] if count_row is not None else 0
        is_admin_flag = existing_count == 0

        cursor.execute(
            """
            INSERT INTO users (email, username, password_hash, is_active, is_admin, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, %s, %s, %s)
            RETURNING id, email, username, is_active, is_admin
            """,
            (email, username, password_hash, is_admin_flag, datetime.utcnow(), datetime.utcnow()),
        )
        row = cursor.fetchone()

    user = dict(row)
    _session_set_user(request, user)

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "is_admin": user["is_admin"],
            "is_active": user["is_active"],
        }
    }


@router.post("/auth/login")
async def login(payload: LoginPayload, request: Request):
    identifier = payload.identifier.strip()
    password = payload.password

    if not identifier or not password:
        raise HTTPException(status_code=400, detail="Missing credentials")

    user = _get_user_by_identifier(identifier)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is disabled")

    stored_hash = user.get("password_hash")
    if not stored_hash or not _verify_password(password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _session_set_user(request, user)

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "is_admin": user["is_admin"],
            "is_active": user["is_active"],
        }
    }


@router.post("/auth/logout")
async def logout(request: Request):
    _session_clear_user(request)
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False, "user": None}

    user = _get_user_by_id(int(user_id))
    if not user or not user.get("is_active", True):
        # Session refers to a missing or disabled user; clear it.
        _session_clear_user(request)
        return {"authenticated": False, "user": None}

    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "is_admin": user["is_admin"],
            "is_active": user["is_active"],
        },
    }
