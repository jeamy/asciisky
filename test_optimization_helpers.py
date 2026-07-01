from datetime import datetime, timezone

import numpy as np
from skyfield.api import Loader
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2
from skyfield.data import mpc

import bright_asteroids
import precompute_coordinator
from api import smart_interpolation
from workers import worker_utils
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


def test_worker_position_bucket_is_hourly_not_legacy_six_hour():
    dt = datetime(2026, 7, 1, 22, 37, tzinfo=timezone.utc)
    assert worker_utils.position_time_bucket(dt) == "20260701T22"


def test_event_grid_step_is_configurable(monkeypatch):
    monkeypatch.setenv("ASCII_SKY_EVENT_GRID_MINUTES", "15")
    ts = Loader("data").timescale()
    anchor = ts.from_datetime(datetime(2026, 6, 30, tzinfo=timezone.utc))
    _, times, step = build_event_time_grid(ts, anchor, days=2)
    assert step == 15
    assert len(times) == 193


def test_smart_interpolation_uses_claimed_high_priority_publisher(monkeypatch):
    published = {}

    def fake_publish(self, **kwargs):
        published.update(kwargs)
        return "comets-test"

    monkeypatch.setattr(
        "api.rabbitmq.task_publisher.TaskPublisher.publish_precompute_task",
        fake_publish,
    )
    smart_interpolation._trigger_background_worker(
        "comets", 46.7632, 14.8417, 405, datetime(2026, 7, 3, 3, tzinfo=timezone.utc)
    )
    assert published["kind"] == "comets"
    assert published["priority"] == 10
    assert published["location"]["latitude"] == 46.7632


def test_comet_frontend_url_uses_ampersand_after_nocache():
    source = open("static/js/skyRenderer.js", encoding="utf-8").read()
    assert "`${API_ENDPOINTS.COMETS}?nocache=1`" in source
    assert "url += `&lat=${this.location.latitude}" in source
