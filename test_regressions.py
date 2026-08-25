from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from api.cache_interpolation import _load_bucket_generic
from api.computation import moon_apparent_magnitude
from api.helpers import parse_time_param
from api.rabbitmq.task_publisher import TaskPublisher
from api.routes import admin_users
from config.interpolation_config import SmartInterpolationConfig
from workers.unified_worker import UnifiedWorker


def test_cache_loader_uses_two_argument_contract_and_preserves_empty_result():
    calls = []

    def loader(location, bucket):
        calls.append((location, bucket))
        return []

    result = _load_bucket_generic(
        48.2,
        16.3,
        171.0,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        1,
        True,
        loader,
    )

    assert result == []
    assert len(calls) == 1


def test_time_parser_converts_offset_instead_of_relabelling_it():
    parsed = parse_time_param("2026-01-01T12:00:00+02:00")
    assert parsed == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def test_time_parser_rejects_invalid_input():
    with pytest.raises(HTTPException) as exc_info:
        parse_time_param("not-a-time")
    assert exc_info.value.status_code == 422


def test_moon_magnitude_is_continuous_and_dimmer_at_new_moon():
    full = moon_apparent_magnitude(1.0)
    nearly_new = moon_apparent_magnitude(1e-9)
    assert full == pytest.approx(-12.7)
    assert nearly_new > full
    assert moon_apparent_magnitude(0.0) == nearly_new


def test_percentage_rollout_uses_stable_digest(monkeypatch):
    monkeypatch.setenv("ENABLE_SMART_INTERPOLATION", "true")
    monkeypatch.setenv("INTERPOLATION_ENABLED_PERCENTAGE", "50")
    first = SmartInterpolationConfig()
    second = SmartInterpolationConfig()
    assert first.is_enabled_for_user("example-user") == second.is_enabled_for_user("example-user")


def test_on_demand_publisher_adds_the_required_task_type(monkeypatch):
    published = {}

    class Channel:
        def basic_publish(self, **kwargs):
            published.update(kwargs)
            return True

    publisher = TaskPublisher("amqp://test")
    monkeypatch.setattr(publisher, "_get_connection", lambda: (object(), Channel()))
    task_id = publisher.publish_on_demand_task(
        {
            "object_type": "asteroids",
            "location": {"latitude": 48.2, "longitude": 16.3, "elevation": 171},
            "time_bucket": "2026-01-01T00:00:00+00:00",
        }
    )

    assert task_id
    assert '"type": "on_demand"' in published["body"]
    assert published["routing_key"] == "compute.asteroid"


def test_cached_on_demand_result_is_a_worker_success():
    class Result:
        class Status:
            value = "cached"

        def __init__(self):
            self.status = self.Status()

    worker = object.__new__(UnifiedWorker)
    worker.on_demand_service = type(
        "Service", (), {"compute_asteroid_bucket": lambda *_args: Result()}
    )()
    worker._publish_status = lambda *_args: None

    assert worker._process_on_demand_task(
        {
            "object_type": "asteroids",
            "location": {"latitude": 48.2, "longitude": 16.3, "elevation": 171},
            "time_bucket": "2026-01-01T00:00:00+00:00",
        }
    )


def test_admin_check_revalidates_the_live_database_role(monkeypatch):
    class Request:
        def __init__(self):
            self.session = {"user_id": 7, "user_is_admin": True}

    monkeypatch.setattr(admin_users, "_get_user_by_id", lambda _user_id: {"id": 7, "is_active": True, "is_admin": False})
    with pytest.raises(HTTPException) as exc_info:
        admin_users._require_admin(Request())
    assert exc_info.value.status_code == 403
