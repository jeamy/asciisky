from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main
import settings as app_settings
from api.routes import filters, user_settings


def _request(session):
    return SimpleNamespace(session=session)


def test_legacy_settings_are_migrated_to_cache(monkeypatch, tmp_path):
    legacy_file = tmp_path / "user_settings.json"
    settings_file = tmp_path / "cache" / "user_settings.json"
    legacy_file.write_text(
        '{"location":{"latitude":1,"longitude":2,"elevation":3},"filters":{"asteroidMaxMagnitude":9,"cometMaxMagnitude":13}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_settings, "LEGACY_SETTINGS_FILE", str(legacy_file))
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(app_settings, "settings", None)

    loaded = app_settings.load_settings()

    assert settings_file.exists()
    assert loaded["location"]["latitude"] == 1
    assert loaded["filters"]["cometMaxMagnitude"] == 13


def test_settings_are_saved_atomically_in_cache_directory(monkeypatch, tmp_path):
    settings_file = tmp_path / "cache" / "user_settings.json"
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(app_settings, "settings", None)

    saved = app_settings.set_magnitude_filters(asteroid_max=11.5, comet_max=15.5)

    assert settings_file.exists()
    assert saved == {"asteroidMaxMagnitude": 11.5, "cometMaxMagnitude": 15.5}
    assert not list(settings_file.parent.glob(".user_settings-*.tmp"))


def test_failed_settings_write_is_propagated_and_rolled_back(monkeypatch, tmp_path):
    settings_file = tmp_path / "cache" / "user_settings.json"
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(app_settings, "settings", app_settings._default_settings())
    previous = app_settings.get_magnitude_filters()
    monkeypatch.setattr(
        app_settings.tempfile,
        "mkstemp",
        lambda **_kwargs: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    with pytest.raises(PermissionError):
        app_settings.set_magnitude_filters(asteroid_max=12.0)

    assert app_settings.get_magnitude_filters() == previous


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


def test_disabled_admin_page_session_is_cleared(monkeypatch):
    session = {"user_id": 3, "user_is_admin": True}
    monkeypatch.setattr(
        main,
        "_get_user_by_id",
        lambda user_id: {"id": user_id, "is_active": False, "is_admin": True},
    )

    assert main._require_admin_page(_request(session)) is None
    assert session == {}


def test_stale_filter_session_is_rejected(monkeypatch):
    session = {"user_id": 4}
    monkeypatch.setattr(filters, "_get_user_by_id", lambda _user_id: None)

    with pytest.raises(HTTPException) as exc:
        filters._resolve_session_user_id(_request(session))

    assert exc.value.status_code == 401
    assert session == {}


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
