from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import user_settings


def _request(session):
    return SimpleNamespace(session=session)


def test_stale_user_session_is_cleared(monkeypatch):
    session = {
        "user_id": 1,
        "user_email": "gone@example.org",
        "user_name": "gone",
        "user_is_admin": False,
    }
    monkeypatch.setattr(user_settings, "_get_user_by_id", lambda _user_id: None)

    with pytest.raises(HTTPException) as exc:
        user_settings._require_authenticated_user(_request(session))

    assert exc.value.status_code == 401
    assert "user_id" not in session
    assert "user_email" not in session


def test_live_user_session_returns_database_id(monkeypatch):
    session = {"user_id": "7"}
    monkeypatch.setattr(
        user_settings,
        "_get_user_by_id",
        lambda user_id: {"id": user_id, "is_active": True},
    )
    assert user_settings._require_authenticated_user(_request(session)) == 7


def test_disabled_user_session_is_cleared(monkeypatch):
    session = {"user_id": 3}
    monkeypatch.setattr(
        user_settings,
        "_get_user_by_id",
        lambda user_id: {"id": user_id, "is_active": False},
    )
    with pytest.raises(HTTPException) as exc:
        user_settings._require_authenticated_user(_request(session))
    assert exc.value.status_code == 401
    assert session == {}
