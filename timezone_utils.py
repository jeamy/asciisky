"""
Timezone utilities: resolve IANA timezone from latitude/longitude and return tzinfo
"""
from functools import lru_cache
from typing import Optional

try:
    from timezonefinder import TimezoneFinder
except Exception:  # pragma: no cover - fallback if not installed
    TimezoneFinder = None  # type: ignore

import pytz

_tf_singleton = None

def _get_tf() -> Optional["TimezoneFinder"]:
    global _tf_singleton
    if _tf_singleton is None and TimezoneFinder is not None:
        try:
            _tf_singleton = TimezoneFinder()
        except Exception:
            _tf_singleton = None
    return _tf_singleton


@lru_cache(maxsize=2048)
def get_timezone_name(lat: float, lon: float) -> str:
    """
    Return IANA timezone name for given coordinates. Fallback to 'UTC' if unknown.
    """
    try:
        tf = _get_tf()
        if tf is None:
            return 'UTC'
        # Try direct match first
        tzname = tf.timezone_at(lat=float(lat), lng=float(lon))
        if tzname:
            return tzname
        # Fallback: closest match
        tzname = tf.closest_timezone_at(lat=float(lat), lng=float(lon))
        if tzname:
            return tzname
    except Exception:
        pass
    return 'UTC'


@lru_cache(maxsize=2048)
def get_tzinfo(lat: float, lon: float):
    """
    Return a pytz timezone for the given coordinates. Defaults to UTC.
    """
    name = get_timezone_name(lat, lon)
    try:
        return pytz.timezone(name)
    except Exception:
        return pytz.timezone('UTC')
