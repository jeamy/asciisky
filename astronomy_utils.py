"""
Shared astronomy helpers used by bright_asteroids.py and comets.py.

Keeps event-grid / rise-set-transit / timescale handling in one place so that
the two modules don't drift apart.
"""
from datetime import timedelta, timezone
from typing import List, Optional, Tuple
import os
import numpy as np


# Standard refraction horizon for rise/set detection (degrees)
DEFAULT_HORIZON_DEG = -0.5667


def format_time(dt, tz=None):
    """
    Formatiert ein datetime-Objekt als lokale Zeit im Format 'HH:MM'.
    Gibt None zurück, wenn dt None ist.
    Wenn tz übergeben wird, wird in diese Zeitzone konvertiert. Naive dt
    wird als UTC interpretiert.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz is None:
        local_time = dt.astimezone()
    else:
        local_time = dt.astimezone(tz)
    return f"{local_time.hour:02d}:{local_time.minute:02d}"


def timescale_from_datetimes(ts, times_dt):
    """Convert a list of Python datetimes to a Skyfield Time array.

    Uses ``ts.from_datetimes`` (plural) available since Skyfield 1.45.
    """
    return ts.from_datetimes(times_dt)


def build_event_time_grid(ts, anchor_time, days: int = 2, minutes_step: int | None = None):
    """Build a Skyfield Time array + matching list of Python datetimes.

    The window starts at the UTC midnight of ``anchor_time`` and spans
    ``days`` days with ``minutes_step`` minute resolution. Returns
    ``(t_grid, times_dt, minutes_step)``.
    """
    if minutes_step is None:
        minutes_step = max(1, int(os.environ.get('ASCII_SKY_EVENT_GRID_MINUTES', '10')))
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
        denom = (y1 - y0)
        if abs(denom) < 1e-15:
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
