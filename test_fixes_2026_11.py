"""Regression tests for the fixes of the code analysis of 2026-11-25.

Each test names the finding it holds (doc/CODE_ANALYSIS_REPORT_2026-11-25.md).
"""
import asyncio
import pickle
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytz
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

import cache_utils
import db_utils
from api import computation
from api.cache_interpolation import load_nearest_bucket
from api.models import LocationPayload, MagnitudeFilters
from api.routes import admin_users, auth, filters, small_bodies
from api.routes import zodiac
from workers.unified_worker import UnifiedWorker

VIENNA = pytz.timezone("Europe/Vienna")


# ----- L1: moon phase names -------------------------------------------------

@pytest.mark.parametrize(
    ("degrees", "name"),
    [
        (0, "new_moon"), (22.4, "new_moon"), (337.6, "new_moon"),
        (45, "waxing_crescent"), (90, "first_quarter"), (135, "waxing_gibbous"),
        (157.6, "full_moon"), (180, "full_moon"), (202.4, "full_moon"),
        (225, "waning_gibbous"), (270, "last_quarter"), (315, "waning_crescent"),
    ],
)
def test_moon_phase_has_eight_sectors_of_45_degrees(degrees, name):
    assert computation.moon_phase_name(degrees) == name


# ----- L14 / O1 / O4: rise, set, transit -----------------------------------

def test_transit_is_the_upper_meridian_transit_not_the_midpoint():
    dt = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    sun = computation.compute_celestial_snapshot(48.2, 16.37, 170.0, dt, only="sun")["bodies"]["sun"]
    # Solar noon in Vienna at the June solstice: about 12:55 CEST.
    hours, minutes = map(int, sun["transit_time"].split(":"))
    assert 12 * 60 + 45 <= hours * 60 + minutes <= 13 * 60 + 5


def test_circumpolar_body_still_gets_a_transit():
    # The Sun in the polar day at 78 N never sets, but it crosses the meridian.
    dt = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    sun = computation.compute_celestial_snapshot(78.2, 15.6, 0.0, dt, only="sun")["bodies"]["sun"]
    assert sun["rise_time"] is None and sun["set_time"] is None
    assert sun["transit_time"] is not None


def test_daily_events_are_cached_per_location_day_and_body(monkeypatch):
    calls = []
    original = computation._search_daily_events

    def counting(body, location, tz, day):
        calls.append(day)
        return original(body, location, tz, day)

    computation._daily_events.clear()
    monkeypatch.setattr(computation, "_search_daily_events", counting)
    dt = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    computation.compute_celestial_snapshot(48.2, 16.37, 170.0, dt, only="mars")
    computation.compute_celestial_snapshot(48.2, 16.37, 170.0, dt + timedelta(minutes=1), only="mars")
    assert len(calls) == 1


def test_single_body_snapshot_computes_only_that_body():
    dt = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    result = computation.compute_celestial_snapshot(48.2, 16.37, 170.0, dt, only="moon")
    assert set(result["bodies"]) == {"moon"}
    assert result["bodies"]["moon"]["phase_name"] in computation._MOON_PHASE_NAMES


# ----- L15: DST-correct local days ------------------------------------------

def test_local_day_spans_23_and_25_hours_on_dst_days():
    spring = computation._local_midnight(date(2026, 3, 30), VIENNA) - computation._local_midnight(date(2026, 3, 29), VIENNA)
    autumn = computation._local_midnight(date(2026, 10, 26), VIENNA) - computation._local_midnight(date(2026, 10, 25), VIENNA)
    assert spring == timedelta(hours=23)
    assert autumn == timedelta(hours=25)
    assert computation.SUNPATH_VERSION >= 6


# ----- L22: time buckets of aware datetimes ---------------------------------

def test_time_bucket_converts_an_offset_to_utc():
    local = datetime(2026, 1, 1, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    assert cache_utils.time_bucket_utc(local, 1) == cache_utils.time_bucket_utc(
        datetime(2025, 12, 31, 23, 30, tzinfo=timezone.utc), 1
    )


def test_nearest_bucket_accepts_naive_utc():
    seen = []
    result = load_nearest_bucket(48.2, 16.3, 171, datetime(2026, 1, 1, 10, 10), 1,
                                 lambda _loc, bucket: seen.append(bucket) or [])
    assert result == []
    assert len(seen) == 1


# ----- S9: cache rows are JSON, never pickle --------------------------------

def test_cache_rows_round_trip_as_json_and_old_pickle_rows_are_a_miss():
    payload = [{"name": "Ceres", "magnitude": 7.1, "when": datetime(2026, 1, 1, tzinfo=timezone.utc)}]
    decoded = db_utils._decode_cache(db_utils._encode_cache(payload))
    assert decoded[0]["name"] == "Ceres"
    assert decoded[0]["when"].startswith("2026-01-01")
    assert db_utils._decode_cache(pickle.dumps(payload)) is None


# ----- L7 / L13: minor-body responses ---------------------------------------

def _run_small_bodies(monkeypatch, bodies, max_magnitude=12.0):
    monkeypatch.setattr(small_bodies, "load_nearest_bucket", lambda *_args: bodies)
    background = BackgroundTasks()
    request = SimpleNamespace(session={})
    result = asyncio.run(small_bodies._small_body_response(
        small_bodies.COMETS, request, background, 48.2, 16.3, 171.0,
        "2026-01-01T10:00:00Z", max_magnitude,
    ))
    return result, background


def test_comet_keys_do_not_depend_on_the_list_order(monkeypatch):
    bodies = [{"name": "C/2025 A1", "magnitude": 9.0}, {"name": "12P", "magnitude": 11.0}]
    first, _ = _run_small_bodies(monkeypatch, bodies)
    second, _ = _run_small_bodies(monkeypatch, list(reversed(bodies)))
    assert set(first["bodies"]) == set(second["bodies"]) == {"comet_C/2025 A1", "comet_12P"}


def test_small_bodies_are_filtered_to_the_callers_limit(monkeypatch):
    bodies = [{"name": "bright", "magnitude": 9.0}, {"name": "faint", "magnitude": 15.0},
              {"name": "unknown", "magnitude": None}]
    result, _ = _run_small_bodies(monkeypatch, bodies, max_magnitude=12.0)
    assert list(result["bodies"]) == ["comet_bright"]


def test_a_cache_miss_requests_the_full_cache_magnitude(monkeypatch):
    result, background = _run_small_bodies(monkeypatch, None, max_magnitude=8.0)
    assert result["bodies"] == {}
    (task,) = background.tasks
    assert task.args[5] == small_bodies.COMETS.module.CACHE_MAX_MAGNITUDE


# ----- L21: unknown and undecodable worker messages -------------------------

class _Channel:
    is_open = True

    def __init__(self):
        self.acked, self.nacked, self.published = [], [], []

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue=True):
        self.nacked.append((delivery_tag, requeue))

    def basic_publish(self, **kwargs):
        self.published.append(kwargs)


def test_undecodable_message_is_dead_lettered_once():
    worker = object.__new__(UnifiedWorker)
    channel = _Channel()
    worker.callback(channel, SimpleNamespace(delivery_tag=3, redelivered=False), None, b"{not json")
    assert channel.acked == [3]
    assert channel.published[0]["routing_key"] == "computation.dead"


def test_unknown_task_kind_is_a_failure():
    worker = object.__new__(UnifiedWorker)
    assert worker._process_precompute_task({"type": "precompute", "kind": "nebulae",
                                "location": {"latitude": 0, "longitude": 0},
                                "time_bucket": "2026-01-01T00:00:00+00:00"}) is False


# ----- S4 / input validation ------------------------------------------------

def test_location_payload_rejects_impossible_coordinates():
    assert LocationPayload(latitude=48.2, longitude=16.3, elevation=None).elevation == 0.0
    for bad in ({"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181},
                {"latitude": 0, "longitude": 0, "elevation": 20000}):
        with pytest.raises(ValidationError):
            LocationPayload(**bad)
    with pytest.raises(ValidationError):
        MagnitudeFilters(asteroidMaxMagnitude=99)


# ----- S1: anonymous filters stay in the session ----------------------------

def test_anonymous_filters_go_to_the_session_not_the_server_defaults(monkeypatch):
    import settings as app_settings

    def refuse(**_kwargs):
        raise AssertionError("anonymous filters must not change the server-wide defaults")

    monkeypatch.setattr(app_settings, "set_magnitude_filters", refuse)
    request = SimpleNamespace(session={})
    answer = filters._set_filters_sync(request, MagnitudeFilters(asteroidMaxMagnitude=11.0))
    assert answer["storage"] == "session"
    assert request.session[filters.SESSION_FILTERS_KEY]["asteroidMaxMagnitude"] == 11.0
    assert filters._get_filters_sync(request)["source"] == "session"


# ----- S6 / L23: login --------------------------------------------------------

def test_disabled_account_is_only_revealed_after_a_correct_password(monkeypatch):
    user = {"id": 1, "is_active": False, "password_hash": auth._hash_password("secret1")}
    monkeypatch.setattr(auth, "_get_user_by_identifier", lambda _identifier: user)
    with pytest.raises(HTTPException) as wrong:
        auth._authenticate_sync("someone", "wrong-password")
    with pytest.raises(HTTPException) as right:
        auth._authenticate_sync("someone", "secret1")
    assert wrong.value.status_code == 401
    assert right.value.status_code == 403


def test_unknown_user_still_verifies_a_password(monkeypatch):
    verified = []
    monkeypatch.setattr(auth, "_get_user_by_identifier", lambda _identifier: None)
    monkeypatch.setattr(auth, "_verify_password", lambda password, stored: verified.append(stored) or False)
    with pytest.raises(HTTPException) as exc_info:
        auth._authenticate_sync("nobody", "whatever")
    assert exc_info.value.status_code == 401
    assert verified == [auth._DUMMY_HASH]


def test_attempt_limiter_blocks_after_the_limit():
    limiter = auth._AttemptLimiter(limit=3, window_seconds=60)
    assert [limiter.hit("k") for _ in range(4)] == [True, True, True, False]
    assert limiter.hit("other") is True


@pytest.mark.parametrize("name", ["ab", "x" * 41, "<script>", "a/b"])
def test_username_rule_rejects_bad_names(name):
    assert not auth._USERNAME_RE.fullmatch(name)


# ----- L24: the last admin ----------------------------------------------------

class _AdminCursor:
    def __init__(self, admin_ids):
        self.admin_ids = admin_ids

    def execute(self, sql, _params=None):
        assert "FOR UPDATE" in sql

    def fetchall(self):
        return [{"id": admin_id} for admin_id in self.admin_ids]


def test_admin_cannot_remove_their_own_admin_access():
    with pytest.raises(HTTPException) as exc_info:
        admin_users._guard_last_admin(_AdminCursor([1, 2]), acting_id=1, target_id=1, removes_admin=True)
    assert exc_info.value.status_code == 400


def test_last_active_admin_cannot_be_removed():
    with pytest.raises(HTTPException):
        admin_users._guard_last_admin(_AdminCursor([2]), acting_id=1, target_id=2, removes_admin=True)
    # Another admin left: allowed.
    admin_users._guard_last_admin(_AdminCursor([2, 3]), acting_id=1, target_id=2, removes_admin=True)
    # Changing a name is no removal.
    admin_users._guard_last_admin(_AdminCursor([1]), acting_id=1, target_id=1, removes_admin=False)


# ----- O19 / L25: zodiac ------------------------------------------------------

def test_zodiac_catalogs_load_once_and_stars_are_positioned():
    dt = datetime(2026, 11, 26, 20, 0, tzinfo=timezone.utc)
    first = zodiac.compute_constellations(48.2, 16.4, 200.0, dt)
    edges = zodiac._constellation_edges
    second = zodiac.compute_constellations(48.2, 16.4, 200.0, dt)
    if first["count"] == 0:
        pytest.skip("Hipparcos or Stellarium data not available")
    assert zodiac._constellation_edges is edges
    assert first == second
    star = first["constellations"][0]["stars"][0]
    assert -90 <= star["altitude"] <= 90 and 0 <= star["azimuth"] < 360


def test_sunpath_route_computes_when_the_cache_is_unreachable(monkeypatch):
    """The cache is best-effort in both directions: a failing read does not fail the request."""
    import asyncio
    from api.routes import celestial as route

    def broken(*_args, **_kwargs):
        raise OSError("database down")

    monkeypatch.setattr(route, "get_cached_sunpath_year", broken)
    monkeypatch.setattr(route, "store_sunpath_year", broken)
    monkeypatch.setattr(route, "compute_sunpath_year", lambda *a: {"version": 6, "points": [{"date": "2026-01-01"}]})
    monkeypatch.setattr(route, "get_location_params", lambda request, lat, lon, elevation: (48.2, 16.37, 170.0))
    result = asyncio.run(route.get_sunpath_year(None, year=2026))
    assert result["points"] == [{"date": "2026-01-01"}]
