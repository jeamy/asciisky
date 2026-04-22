"""
Shared astronomy helpers used by bright_asteroids.py and comets.py.

Keeps event-grid / rise-set-transit / timescale handling in one place so that
the two modules don't drift apart.
"""
from datetime import timedelta
from typing import List, Optional, Tuple
import numpy as np


# Standard refraction horizon for rise/set detection (degrees)
DEFAULT_HORIZON_DEG = -0.5667


def timescale_from_datetimes(ts, times_dt):
    """Convert a list of Python datetimes to a Skyfield Time array.

    Skyfield >= 1.45 offers ``ts.from_datetimes`` (plural); fall back to the
    classic ``ts.utc`` scalar-array API for older versions.
    """
    if hasattr(ts, "from_datetimes"):
        return ts.from_datetimes(times_dt)
    years = [dt.year for dt in times_dt]
    months = [dt.month for dt in times_dt]
    days = [dt.day for dt in times_dt]
    hours = [dt.hour for dt in times_dt]
    minutes = [dt.minute for dt in times_dt]
    seconds = [dt.second + dt.microsecond / 1e6 for dt in times_dt]
    return ts.utc(years, months, days, hours, minutes, seconds)


def build_event_time_grid(ts, anchor_time, days: int = 2, minutes_step: int = 5):
    """Build a Skyfield Time array + matching list of Python datetimes.

    The window starts at the UTC midnight of ``anchor_time`` and spans
    ``days`` days with ``minutes_step`` minute resolution. Returns
    ``(t_grid, times_dt, minutes_step)``.
    """
    start_dt = anchor_time.utc_datetime().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=days)
    total_minutes = int((end_dt - start_dt).total_seconds() / 60)
    steps = total_minutes // minutes_step
    times_dt = [start_dt + timedelta(minutes=i * minutes_step) for i in range(steps + 1)]
    t_grid = timescale_from_datetimes(ts, times_dt)
    return t_grid, times_dt, minutes_step


def compute_rise_set_transit_from_altitudes(
    alt_deg: np.ndarray,
    times_dt: List,
    minutes_step: int,
    horizon_deg: float = DEFAULT_HORIZON_DEG,
) -> Tuple[Optional[object], Optional[object], Optional[object]]:
    """Extract first rise, first set and transit (max altitude) from a
    pre-computed altitude grid.

    ``alt_deg`` must be a 1D NumPy array of altitudes (deg) sampled at the
    timestamps in ``times_dt``. Rise/set are detected via linear interpolation
    at zero-crossings of ``alt - horizon``; transit is the argmax of ``alt``.

    Returns ``(rise_time, set_time, transit_time)`` with tz-aware datetimes
    (copied from ``times_dt`` which are tz-aware) or ``None`` when no event
    was found in the window.
    """
    rise_time = None
    set_time = None
    transit_time = None

    if alt_deg is None or len(alt_deg) == 0:
        return rise_time, set_time, transit_time

    alt_shifted = alt_deg - horizon_deg
    sign_change = (alt_shifted[:-1] * alt_shifted[1:]) < 0
    indices = np.where(sign_change)[0]

    for i in indices:
        y0 = alt_shifted[i]
        y1 = alt_shifted[i + 1]
        # Guard against division by zero (shouldn't happen with strict sign
        # change, but floats...)
        denom = (y1 - y0)
        if denom == 0:
            continue
        fraction = -y0 / denom
        event_dt = times_dt[i] + timedelta(minutes=minutes_step * fraction)

        if y0 < 0 and rise_time is None:
            rise_time = event_dt
        elif y0 > 0 and set_time is None:
            set_time = event_dt
        if rise_time is not None and set_time is not None:
            break

    # Transit = global max within the window
    try:
        max_idx = int(np.argmax(alt_deg))
        transit_time = times_dt[max_idx]
    except Exception:
        transit_time = None

    return rise_time, set_time, transit_time


def compute_rise_set_transit(observer, target, t_grid, times_dt, minutes_step,
                             horizon_deg: float = DEFAULT_HORIZON_DEG):
    """Convenience wrapper: sample altitude grid for a single target and
    extract rise/set/transit. Returns ``(rise_time, set_time, transit_time)``.
    """
    grid_obs = observer.at(t_grid).observe(target)
    grid_alt, _grid_az, _ = grid_obs.apparent().altaz()
    return compute_rise_set_transit_from_altitudes(
        grid_alt.degrees, times_dt, minutes_step, horizon_deg
    )
