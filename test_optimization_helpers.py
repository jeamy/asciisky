from datetime import datetime, timezone

import numpy as np
from skyfield.api import Loader
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc

import bright_asteroids
import precompute_coordinator
from astronomy_utils import build_event_time_grid
from workers import worker_utils


def test_packed_epoch_decoder_matches_skyfield():
    loader = Loader("data")
    ts = loader.timescale()
    values = np.array(["K239N", "K256U", "J9912"])
    decoded = bright_asteroids._packed_mpc_epochs_tt(values)

    class Row:
        semimajor_axis_au = 2.5
        eccentricity = 0.1
        inclination_degrees = 1.0
        longitude_of_ascending_node_degrees = 2.0
        argument_of_perihelion_degrees = 3.0
        mean_anomaly_degrees = 4.0
        designation = "test"

    expected = []
    for value in values:
        row = Row()
        row.epoch_packed = value
        orbit = mpc.mpcorb_orbit(row, ts, gm_km3_s2=GM_SUN_Pitjeva_2005_km3_s2)
        expected.append(orbit.epoch.tt)
    np.testing.assert_allclose(decoded, expected, rtol=0.0, atol=0.0)


def test_packed_epoch_decoder_ignores_mpc_header_rows():
    decoded = bright_asteroids._packed_mpc_epochs_tt(
        np.array(["ORBIT", "This ", "K239N", None], dtype=object)
    )
    assert np.isnan(decoded[0])
    assert np.isnan(decoded[1])
    assert np.isfinite(decoded[2])
    assert np.isnan(decoded[3])


def test_precompute_prioritizes_current_and_adjacent_hours():
    assert precompute_coordinator.task_priority(0) == 10
    assert precompute_coordinator.task_priority(-1) == 9
    assert precompute_coordinator.task_priority(1) == 9
    assert precompute_coordinator.task_priority(-2) == 8
    assert precompute_coordinator.task_priority(2) == 8
    assert precompute_coordinator.task_priority(6) > precompute_coordinator.task_priority(72)


def test_coordinator_tasks_use_configured_bucket_boundary(monkeypatch):
    monkeypatch.setattr(precompute_coordinator.bright_asteroids, "ASTEROID_CACHE_BUCKET_HOURS", 6)
    monkeypatch.setattr(precompute_coordinator.comets, "COMET_CACHE_BUCKET_HOURS", 3)
    monkeypatch.setattr(precompute_coordinator, "get_asteroid_positions", lambda *args: None)
    monkeypatch.setattr(precompute_coordinator, "get_comet_positions", lambda *args: None)

    tasks = precompute_coordinator.create_precompute_tasks(
        [{"latitude": 46.7632, "longitude": 14.8417, "elevation": 405}],
        0,
        1,
        include_yearly=False,
    )
    asteroid_task = next(task for task in tasks if task["kind"] == "asteroids")
    comet_task = next(task for task in tasks if task["kind"] == "comets")

    assert asteroid_task["bucket_hours"] == 6
    assert datetime.fromisoformat(asteroid_task["time_bucket"]).hour % 6 == 0
    assert comet_task["bucket_hours"] == 3
    assert datetime.fromisoformat(comet_task["time_bucket"]).hour % 3 == 0


def test_worker_position_bucket_is_hourly_not_legacy_six_hour():
    dt = datetime(2026, 7, 1, 22, 37, tzinfo=timezone.utc)
    assert worker_utils.position_time_bucket(dt) == "20260701T22"


def test_worker_position_bucket_uses_task_bucket_hours():
    dt = datetime(2026, 7, 1, 22, 37, tzinfo=timezone.utc)
    assert worker_utils.position_time_bucket(dt, 6) == "20260701T18"


def test_precompute_task_key_includes_bucket_size():
    task = {
        "kind": "comets",
        "location": {"latitude": 46.7632, "longitude": 14.8417, "elevation": 405},
        "time_bucket": "2026-07-01T22:37:00+00:00",
        "bucket_hours": 6,
    }
    assert worker_utils.precompute_task_key(task).endswith("20260701T18_6h")




def test_event_grid_step_is_configurable(monkeypatch):
    monkeypatch.setenv("ASCII_SKY_EVENT_GRID_MINUTES", "15")
    ts = Loader("data").timescale()
    anchor = ts.from_datetime(datetime(2026, 6, 30, tzinfo=timezone.utc))
    _, times, step = build_event_time_grid(ts, anchor, days=2)
    assert step == 15
    assert len(times) == 193
