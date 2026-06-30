from datetime import datetime, timezone

import numpy as np
from skyfield.api import Loader
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc

import bright_asteroids
import precompute_coordinator
from astronomy_utils import build_event_time_grid


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


def test_precompute_prioritizes_current_and_adjacent_hours():
    assert precompute_coordinator.task_priority(0) == 10
    assert precompute_coordinator.task_priority(-1) == 9
    assert precompute_coordinator.task_priority(1) == 9
    assert precompute_coordinator.task_priority(6) > precompute_coordinator.task_priority(72)


def test_event_grid_step_is_configurable(monkeypatch):
    monkeypatch.setenv("ASCII_SKY_EVENT_GRID_MINUTES", "15")
    ts = Loader("data").timescale()
    anchor = ts.from_datetime(datetime(2026, 6, 30, tzinfo=timezone.utc))
    _, times, step = build_event_time_grid(ts, anchor, days=2)
    assert step == 15
    assert len(times) == 193
