"""
Timezone utilities: resolve IANA timezone from latitude/longitude and return tzinfo
"""
import threading
from functools import lru_cache
from typing import Optional

try:
    from timezonefinder import TimezoneFinder
except Exception:  # pragma: no cover - fallback if not installed
    TimezoneFinder = None  # type: ignore

import pytz

_tf_singleton = None
# TimezoneFinder reads its polygon files on demand and is not documented as
# thread-safe; one lock covers both its construction and its lookups.
_tf_lock = threading.Lock()


def _get_tf() -> Optional["TimezoneFinder"]:
    """Return the process-wide TimezoneFinder; call with ``_tf_lock`` held."""
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
        with _tf_lock:
            tf = _get_tf()
            if tf is None:
                return 'UTC'
            tzname = tf.timezone_at(lat=float(lat), lng=float(lon))
            if not tzname and hasattr(tf, 'closest_timezone_at'):
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
