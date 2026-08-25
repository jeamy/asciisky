from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import pickle
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.cache_interpolation import _load_bucket_generic
from api import computation as computation_module
from api.computation import (
    moon_apparent_magnitude,
    _ensure_utc,
    _to_hours,
    _serialize_dt,
    _serialize_periods,
    _merge_sorted_periods,
    _twilight_boundaries,
    _localize_naive,
    _compute_transit_time,
    _body_magnitude,
    _build_body_entry,
    _add_moon_phase,
    compute_celestial_snapshot,
    compute_sunpath_year,
)
from api.helpers import parse_time_param
from api.on_demand_computation import OnDemandComputationConfig, OnDemandComputationService
from api.rabbitmq import task_publisher
from api.rabbitmq.task_publisher import TaskPublisher
from api.routes import admin_users
from config.interpolation_config import InterpolationConfigManager, SmartInterpolationConfig
import db_utils
import precompute_coordinator
from workers import worker_utils
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


def test_precompute_coordinator_preserves_empty_cached_results(monkeypatch):
    monkeypatch.setattr(precompute_coordinator, "get_asteroid_positions", lambda *_args: [])
    monkeypatch.setattr(precompute_coordinator, "get_comet_positions", lambda *_args: [])

    tasks = precompute_coordinator.create_precompute_tasks(
        [{"latitude": 48.2, "longitude": 16.3, "elevation": 171}],
        0,
        1,
        include_yearly=False,
    )

    assert tasks == []


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


def test_interpolation_manager_handles_concurrent_user_updates():
    manager = InterpolationConfigManager()
    user_ids = [f"user-{index}" for index in range(100)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(manager.enable_for_user, user_ids))

    config = manager.get_config()
    assert sorted(config.enabled_user_ids) == sorted(user_ids)
    config.enabled_user_ids.clear()
    assert sorted(manager.get_config().enabled_user_ids) == sorted(user_ids)


def test_percentage_rollout_uses_stable_digest(monkeypatch):
    monkeypatch.setenv("ENABLE_SMART_INTERPOLATION", "true")
    monkeypatch.setenv("INTERPOLATION_ENABLED_PERCENTAGE", "50")
    first = SmartInterpolationConfig()
    second = SmartInterpolationConfig()
    assert first.is_enabled_for_user("example-user") == second.is_enabled_for_user("example-user")


def test_on_demand_metrics_are_consistent_under_concurrency():
    config = OnDemandComputationConfig()
    config.cache_ttl = 0
    config.trigger_background_tasks = False
    service = OnDemandComputationService(config)

    def compute(index):
        return service._compute_bucket(
            "asteroids",
            48.2,
            16.3,
            171,
            datetime(2026, 1, 1, index % 24, tzinfo=timezone.utc),
            True,
            lambda *_args: [],
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compute, range(100)))

    metrics = service.get_metrics()
    assert all(result.status.value == "success" for result in results)
    assert metrics.total_computations == 100
    assert metrics.successful_computations == 100


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


def test_publisher_releases_claim_after_negative_confirm(monkeypatch):
    released = []

    class Channel:
        def basic_publish(self, **_kwargs):
            return False

    publisher = TaskPublisher("amqp://test")
    monkeypatch.setattr(publisher, "_get_connection", lambda: (object(), Channel()))
    monkeypatch.setattr(task_publisher, "claim_precompute_task", lambda _key: True)
    monkeypatch.setattr(task_publisher, "release_precompute_task", released.append)

    with pytest.raises(RuntimeError):
        publisher.publish_precompute_task(
            "asteroids",
            {"latitude": 48.2, "longitude": 16.3, "elevation": 171},
            "2026-01-01T00:00:00+00:00",
        )

    assert len(released) == 1


def test_worker_routes_second_failure_to_dlq_and_releases_claim(monkeypatch):
    released = []

    class Channel:
        is_open = True

        def __init__(self):
            self.acked = []
            self.published = []

        def basic_ack(self, delivery_tag):
            self.acked.append(delivery_tag)

        def basic_publish(self, **kwargs):
            self.published.append(kwargs)

    task = {
        "type": "precompute",
        "kind": "asteroids",
        "location": {"latitude": 48.2, "longitude": 16.3, "elevation": 171},
        "time_bucket": "2026-01-01T00:00:00+00:00",
    }
    worker = object.__new__(UnifiedWorker)
    worker.process_task = lambda _task: False
    monkeypatch.setattr(db_utils, "release_precompute_task", released.append)
    channel = Channel()

    worker.callback(
        channel,
        SimpleNamespace(delivery_tag=7, redelivered=True),
        None,
        json.dumps(task),
    )

    assert len(released) == 1
    assert channel.acked == [7]
    assert channel.published[0]["routing_key"] == "computation.dead"


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


def test_dataframe_resources_reload_after_source_change(monkeypatch, tmp_path):
    asteroid_path = tmp_path / "asteroid_dataframe.pkl"
    comet_path = tmp_path / "comet_dataframe.pkl"
    asteroid_path.write_bytes(b"first")
    comet_path.write_bytes(b"comet")
    payloads = {
        "asteroid": pickle.dumps(["old"]),
        "comet": pickle.dumps(["comet"]),
    }
    resources = object.__new__(worker_utils.SharedSkyfieldResources)
    resources.asteroid_df = None
    resources.comet_df = None
    resources._dataframe_mtimes = {}
    monkeypatch.setattr("data_paths.DATA_DIR", tmp_path)
    monkeypatch.setattr(db_utils, "get_asteroid_dataframe", lambda: payloads["asteroid"])
    monkeypatch.setattr(db_utils, "get_comet_dataframe", lambda: payloads["comet"])

    resources._reload_dataframes(force=True)
    payloads["asteroid"] = pickle.dumps(["new"])
    asteroid_path.write_bytes(b"second-version")
    stat = asteroid_path.stat()
    os.utime(asteroid_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    resources._reload_dataframes()

    assert resources.asteroid_df == ["new"]


def test_stale_dataframe_is_an_explicit_miss(monkeypatch, tmp_path):
    path = tmp_path / "asteroid_dataframe.pkl"
    path.write_bytes(b"payload")
    monkeypatch.setattr("data_paths.DATA_DIR", tmp_path)
    monkeypatch.setattr(db_utils.time, "time", lambda: path.stat().st_mtime + 10)

    assert db_utils.get_asteroid_dataframe(max_age_seconds=5) is None


def test_admin_check_revalidates_the_live_database_role(monkeypatch):
    class Request:
        def __init__(self):
            self.session = {"user_id": 7, "user_is_admin": True}

    monkeypatch.setattr(admin_users, "_get_user_by_id", lambda _user_id: {"id": 7, "is_active": True, "is_admin": False})
    with pytest.raises(HTTPException) as exc_info:
        admin_users._require_admin(Request())
    assert exc_info.value.status_code == 403


def test_ensure_utc_normalizes_naive_and_aware_to_utc():
    naive = datetime(2026, 6, 21, 12, 0)
    assert _ensure_utc(naive).tzinfo is timezone.utc
    assert _ensure_utc(naive) == datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    aware = datetime(2026, 6, 21, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    normalized = _ensure_utc(aware)
    assert normalized.tzinfo is timezone.utc
    assert normalized == datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    already_utc = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    assert _ensure_utc(already_utc) == already_utc


def test_to_hours_converts_and_handles_none():
    assert _to_hours(None) is None
    assert _to_hours(datetime(2026, 1, 1, 6, 30, 45)) == pytest.approx(6.5125)


def test_serialize_dt_handles_none_and_datetime():
    assert _serialize_dt(None) is None
    dt = datetime(2026, 6, 21, 5, 0, tzinfo=timezone.utc)
    assert _serialize_dt(dt) == "2026-06-21T05:00:00+00:00"


def test_serialize_periods_empty_and_nonempty():
    assert _serialize_periods([]) == []
    dt = datetime(2026, 6, 21, 5, 0, tzinfo=timezone.utc)
    assert _serialize_periods([(dt, dt)]) == [
        {"start": "2026-06-21T05:00:00+00:00", "end": "2026-06-21T05:00:00+00:00"}
    ]


def test_merge_sorted_periods_merges_and_skips_disjoint():
    base = datetime(2026, 6, 21, tzinfo=timezone.utc)
    a = base
    b = base + timedelta(hours=2)
    c = base + timedelta(hours=3)
    d = base + timedelta(hours=5)

    assert _merge_sorted_periods([(a, b), (b, c)]) == [(a, c)]
    assert _merge_sorted_periods([(a, b), (c, d)]) == [(a, b), (c, d)]
    assert _merge_sorted_periods([]) == []


def test_twilight_boundaries_empty_and_mixed():
    empty = {"astronomical": [], "nautical": [], "civil": []}
    assert _twilight_boundaries(empty) == (None, None, None, None, None, None)

    base = datetime(2026, 6, 21, tzinfo=timezone.utc)
    periods = {
        "astronomical": [(base + timedelta(hours=1), base + timedelta(hours=2))],
        "nautical": [(base + timedelta(hours=3), base + timedelta(hours=4))],
        "civil": [(base + timedelta(hours=5), base + timedelta(hours=6))],
    }
    astro_start, astro_end, naut_start, naut_end, civil_start, civil_end = _twilight_boundaries(periods)
    assert astro_start == base + timedelta(hours=1)
    assert astro_end == base + timedelta(hours=2)
    assert naut_start == base + timedelta(hours=3)
    assert naut_end == base + timedelta(hours=4)
    assert civil_start == base + timedelta(hours=5)
    assert civil_end == base + timedelta(hours=6)


def test_localize_naive_handles_pytz_and_stdlib():
    class FakePytzZone:
        def localize(self, naive):
            return naive.replace(tzinfo=timezone.utc)

    stdlib_zone = timezone.utc
    assert _localize_naive(datetime(2026, 1, 1), stdlib_zone).tzinfo is timezone.utc
    assert _localize_naive(datetime(2026, 1, 1), FakePytzZone()).tzinfo is timezone.utc


def test_compute_transit_time_returns_midpoint():
    tz = timezone.utc
    local_dt = datetime(2026, 6, 21, tzinfo=tz)
    assert _compute_transit_time("06:00", "18:00", tz, local_dt) == "12:00"
    assert _compute_transit_time("22:00", "04:00", tz, local_dt) == "01:00"


def test_body_magnitude_for_sun_and_outer_planets():
    assert _body_magnitude("sun", None, None) == -26.74
    assert _body_magnitude("uranus", None, None) == 5.7
    assert _body_magnitude("neptune", None, None) == 7.8
    assert _body_magnitude("unknown_body", None, None) == 0


def test_body_magnitude_falls_back_for_inner_planets(monkeypatch):
    monkeypatch.setattr(computation_module, "planetary_magnitude", lambda _astrometric: (_ for _ in ()).throw(Exception("boom")))
    assert _body_magnitude("mercury", object(), None) == 0.23
    assert _body_magnitude("venus", object(), None) == -4.14


def test_build_body_entry_has_expected_schema():
    class FakeAngle:
        degrees = 45.0

    entry = _build_body_entry(
        "mars", FakeAngle(), FakeAngle(), 1.5, 1.66, "06:00", "18:00", "12:00"
    )
    assert entry["name"] == "mars"
    assert entry["symbol"] == "♂"
    assert entry["altitude"] == 45.0
    assert entry["azimuth"] == 45.0
    assert entry["distance"] == 1.5
    assert entry["magnitude"] == 1.66
    assert entry["visible"] is True
    assert entry["rise_time"] == "06:00"
    assert entry["set_time"] == "18:00"
    assert entry["transit_time"] == "12:00"


def test_add_moon_phase_sets_phase_and_name(monkeypatch):
    class FakeAstrometric:
        def fraction_illuminated(self, _sun):
            return 0.75

    class FakePhase:
        degrees = 120.0

    monkeypatch.setattr(computation_module.almanac, "moon_phase", lambda _eph, _t: FakePhase())
    body_entry = {}
    _add_moon_phase(body_entry, FakeAstrometric(), None)
    assert body_entry["phase"] == 0.75
    assert body_entry["phase_name"] == "waxing_gibbous"


def test_compute_celestial_snapshot_schema_is_preserved():
    dt = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    result = compute_celestial_snapshot(48.2, 16.37, 170.0, dt)

    assert result["time"] == dt.isoformat()
    assert result["location"] == {"latitude": 48.2, "longitude": 16.37, "elevation": 170.0}
    assert result["loading"] is False
    assert set(result["bodies"]) == set(computation_module.CELESTIAL_BODIES)

    for name, entry in result["bodies"].items():
        expected_keys = {
            "name", "symbol", "altitude", "azimuth", "distance", "magnitude",
            "visible", "transit_time", "rise_time", "set_time",
        }
        if name == "moon":
            expected_keys |= {"phase", "phase_name"}
        assert set(entry) == expected_keys
        assert isinstance(entry["altitude"], float)
        assert isinstance(entry["azimuth"], float)
        assert isinstance(entry["distance"], float)
        assert isinstance(entry["magnitude"], float)


def test_compute_sunpath_year_schema_is_preserved():
    result = compute_sunpath_year(48.2, 16.37, 170.0, 2026)

    assert result["version"] == computation_module.SUNPATH_VERSION
    assert result["year"] == 2026
    assert result["location"]["latitude"] == 48.2
    assert result["location"]["longitude"] == 16.37
    assert result["location"]["elevation"] == 170.0
    assert "timezone" in result["location"]
    assert len(result["points"]) == 365

    point = result["points"][0]
    expected_keys = {
        "date", "sunrise", "sunset", "sunrise_hours", "sunset_hours",
        "transit", "transit_hours", "day_length_hours",
        "astronomical_twilight_start", "astronomical_twilight_end",
        "nautical_twilight_start", "nautical_twilight_end",
        "civil_twilight_start", "civil_twilight_end",
        "astronomical_twilight_periods", "nautical_twilight_periods",
        "civil_twilight_periods",
    }
    assert set(point) == expected_keys
