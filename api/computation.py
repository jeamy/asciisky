import logging
import math
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from skyfield import almanac
from skyfield.api import Loader, wgs84
from skyfield.magnitudelib import planetary_magnitude

from data_paths import DATA_DIR
from timezone_utils import get_tzinfo

logger = logging.getLogger(__name__)

# Load Skyfield data
LOADER = Loader(str(DATA_DIR))
ts = LOADER.timescale()
eph = LOADER('de421.bsp')  # Nur Dateiname, nicht vollständiger Pfad

# Celestial bodies and their symbols
CELESTIAL_BODIES = {
    'sun': eph['sun'],
    'moon': eph['moon'],
    'mercury': eph['mercury'],
    'venus': eph['venus'],
    'mars': eph['mars'],
    'jupiter': eph['jupiter barycenter'],
    'saturn': eph['saturn barycenter'],
    'uranus': eph['uranus barycenter'],
    'neptune': eph['neptune barycenter']
}

BODY_SYMBOLS = {
    'sun': '☀️',
    'moon': '🌙',
    'mercury': '☿',
    'venus': '♀',
    'mars': '♂',
    'jupiter': '♃',
    'saturn': '♄',
    'uranus': '♅',
    'neptune': '♆',
    'comet': '☄️',
    'asteroid': '⚸'
}

_DEFAULT_MAGNITUDES = {
    'sun': -26.74,
    'mercury': 0.23,
    'venus': -4.14,
    'mars': 1.66,
    'jupiter': -2.2,
    'saturn': 0.46,
    'uranus': 5.7,
    'neptune': 7.8,
}


def moon_apparent_magnitude(phase_factor: float) -> float:
    """Return a finite, continuous apparent magnitude for the Moon."""
    return -12.7 - 2.5 * math.log10(max(float(phase_factor), 1e-6))


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _compute_body_position(body, observer_at, earth_at):
    """Return apparent alt/az and Earth-center distance (au) for a body.

    ``observer_at`` and ``earth_at`` are the observer's and the geocenter's
    positions at the snapshot time, computed once per snapshot.
    """
    astrometric = observer_at.observe(body)
    alt, az, _distance = astrometric.apparent().altaz()
    earth_distance = earth_at.observe(body).distance().au
    return astrometric, alt, az, earth_distance


def _moon_phase_factor(phase_degrees: float) -> float:
    return 0.5 * (1 - math.cos(math.radians(phase_degrees)))


def _body_magnitude(name: str, astrometric, moon_phase_degrees: float | None = None) -> float:
    if name == 'sun':
        return _DEFAULT_MAGNITUDES['sun']

    if name == 'moon':
        return moon_apparent_magnitude(_moon_phase_factor(moon_phase_degrees or 0.0))

    if name in ('mercury', 'venus', 'mars', 'jupiter', 'saturn'):
        try:
            return planetary_magnitude(astrometric)
        except Exception:
            return _DEFAULT_MAGNITUDES.get(name, 0)

    return _DEFAULT_MAGNITUDES.get(name, 0)


# Rise, set and transit change once per local day: cache them per rounded
# location, local date and body (``/celestial`` is polled every minute).
_DAILY_EVENTS_MAX = 4096
_daily_events: OrderedDict[tuple, tuple[str | None, str | None, str | None]] = OrderedDict()
_daily_events_lock = threading.Lock()


def _search_daily_events(body, location, tz, day) -> tuple[str | None, str | None, str | None]:
    """First rise, first set and upper transit within the local day, as '%H:%M'."""
    start = _local_midnight(day, tz)
    end = _local_midnight(day + timedelta(days=1), tz)
    t0 = ts.from_datetime(start)
    t1 = ts.from_datetime(end)

    rise_time = set_time = transit_time = None
    times, events = almanac.find_discrete(t0, t1, almanac.risings_and_settings(eph, body, location))
    for ti, event in zip(times, events):
        local = ti.utc_datetime().astimezone(tz)
        if event == 1 and rise_time is None:
            rise_time = local.strftime('%H:%M')
        elif event == 0 and set_time is None:
            set_time = local.strftime('%H:%M')

    times, events = almanac.find_discrete(t0, t1, almanac.meridian_transits(eph, body, location))
    for ti, event in zip(times, events):
        if event == 1:  # upper transit
            transit_time = ti.utc_datetime().astimezone(tz).strftime('%H:%M')
            break
    return rise_time, set_time, transit_time


def _find_rise_set_transit(name: str, body, location, tz, dt_utc: datetime, loc_key: tuple):
    """Return (rise_time, set_time, transit_time) of the local day as '%H:%M' or None."""
    day = dt_utc.astimezone(tz).date()
    key = (loc_key, day, name)
    with _daily_events_lock:
        cached = _daily_events.get(key)
        if cached is not None:
            _daily_events.move_to_end(key)
            return cached
    result = _search_daily_events(body, location, tz, day)
    with _daily_events_lock:
        _daily_events[key] = result
        while len(_daily_events) > _DAILY_EVENTS_MAX:
            _daily_events.popitem(last=False)
    return result


def _build_body_entry(
    name: str,
    alt,
    az,
    earth_distance: float,
    mag: float,
    rise_time,
    set_time,
    transit_time,
) -> dict:
    return {
        "name": name,
        "symbol": BODY_SYMBOLS.get(name, "?"),
        "altitude": float(alt.degrees),
        "azimuth": float(az.degrees),
        "distance": float(earth_distance),
        "magnitude": float(mag),
        "visible": True,
        "transit_time": transit_time,
        "rise_time": rise_time,
        "set_time": set_time,
    }


_MOON_PHASE_NAMES = (
    "new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous",
    "full_moon", "waning_gibbous", "last_quarter", "waning_crescent",
)


def moon_phase_name(phase_degrees: float) -> str:
    """Name of the phase: eight sectors of 45 degrees, each centered on its phase."""
    return _MOON_PHASE_NAMES[int(((phase_degrees + 22.5) % 360) // 45)]


def _add_moon_phase(body_entry: dict, astrometric, phase_degrees: float) -> None:
    body_entry["phase"] = astrometric.fraction_illuminated(eph['sun'])
    body_entry["phase_name"] = moon_phase_name(phase_degrees)


def compute_celestial_snapshot(
    lat: float, lon: float, elevation: float, dt_utc: datetime, only: str | None = None,
) -> dict:
    """Positions, magnitudes and daily events of the solar system bodies.

    ``only`` restricts the snapshot to one body (``/celestial/{body_id}``).
    """
    dt_utc = _ensure_utc(dt_utc)

    tz = get_tzinfo(lat, lon)
    t = ts.from_datetime(dt_utc)
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer_at = (eph['earth'] + location).at(t)
    earth_at = eph['earth'].at(t)
    loc_key = (round(lat, 4), round(lon, 4), round(elevation))

    result = {
        "time": dt_utc.isoformat(),
        "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
        "bodies": {},
        "loading": False
    }

    bodies = CELESTIAL_BODIES.items() if only is None else [(only, CELESTIAL_BODIES[only])]
    moon_phase_degrees = None
    if only in (None, 'moon'):
        moon_phase_degrees = float(almanac.moon_phase(eph, t).degrees)

    for name, body in bodies:
        try:
            astrometric, alt, az, earth_distance = _compute_body_position(body, observer_at, earth_at)
            mag = _body_magnitude(name, astrometric, moon_phase_degrees)

            try:
                rise_time, set_time, transit_time = _find_rise_set_transit(
                    name, body, location, tz, dt_utc, loc_key)
            except Exception:
                logger.debug("Rise/set search failed for %s", name, exc_info=True)
                rise_time, set_time, transit_time = None, None, None

            body_entry = _build_body_entry(
                name, alt, az, earth_distance, mag,
                rise_time, set_time, transit_time,
            )

            if name == 'moon':
                _add_moon_phase(body_entry, astrometric, moon_phase_degrees)

            result["bodies"][name] = body_entry
        except Exception:
            logger.exception("Error calculating position for %s", name)

    return result


# 6: twilight day windows end at the next local midnight on DST days (L15),
#    the upper transit is taken from the event type.
SUNPATH_VERSION = 6


def _local_midnight(day: datetime, tz) -> datetime:
    """Return local midnight for given date, handling pytz and stdlib timezones."""
    naive = datetime(day.year, day.month, day.day)
    try:
        if hasattr(tz, "localize"):
            return tz.localize(naive)
    except Exception:
        pass
    return naive.replace(tzinfo=tz)


def _to_hours(dt) -> float | None:
    if dt is None:
        return None
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0


def _build_sun_events_by_date(times, events, tz):
    sun_events_by_date = {}
    for ti, ev in zip(times, events):
        dt_local = ti.utc_datetime().astimezone(tz)
        d = dt_local.date()
        if d not in sun_events_by_date:
            sun_events_by_date[d] = {'sunrise': None, 'sunset': None}

        if ev == 1 and sun_events_by_date[d]['sunrise'] is None:
            sun_events_by_date[d]['sunrise'] = dt_local
        elif ev == 0 and sun_events_by_date[d]['sunset'] is None:
            sun_events_by_date[d]['sunset'] = dt_local
    return sun_events_by_date


def _build_transit_events_by_date(transit_times, transit_events, tz):
    """Local time of the upper transit (event 1) per local date."""
    transit_events_by_date = {}
    for ti, ev in zip(transit_times, transit_events):
        if ev != 1:
            continue
        dt_local = ti.utc_datetime().astimezone(tz)
        transit_events_by_date.setdefault(dt_local.date(), dt_local)
    return transit_events_by_date


def _build_twilight_segments(t_start, t_end, twilight_f):
    try:
        tw_times, tw_states = almanac.find_discrete(t_start, t_end, twilight_f)
        initial_state = int(twilight_f(t_start))

        all_segments = []
        last_time_utc = t_start.utc_datetime()
        last_state = initial_state

        for ti, st in zip(tw_times, tw_states):
            ti_utc = ti.utc_datetime()
            all_segments.append((last_time_utc, ti_utc, last_state))
            last_time_utc = ti_utc
            last_state = int(st)
        all_segments.append((last_time_utc, t_end.utc_datetime(), last_state))

        return True, all_segments
    except Exception:
        return False, []


def _collect_twilight_periods(day_start_local, day_end_local, segments, segment_idx, tz):
    raw_periods = {'astronomical': [], 'nautical': [], 'civil': []}
    num_segments = len(segments)

    while segment_idx < num_segments:
        seg_end_utc = segments[segment_idx][1]
        if seg_end_utc.astimezone(tz) > day_start_local:
            break
        segment_idx += 1

    temp_idx = segment_idx
    while temp_idx < num_segments:
        seg_start_utc, seg_end_utc, state = segments[temp_idx]
        seg_start_local = seg_start_utc.astimezone(tz)

        if seg_start_local >= day_end_local:
            break

        seg_end_local = seg_end_utc.astimezone(tz)
        start_local_clipped = max(seg_start_local, day_start_local)
        end_local_clipped = min(seg_end_local, day_end_local)

        if end_local_clipped > start_local_clipped:
            if state == 1:
                raw_periods['astronomical'].append((start_local_clipped, end_local_clipped))
            elif state == 2:
                raw_periods['nautical'].append((start_local_clipped, end_local_clipped))
            elif state == 3:
                raw_periods['civil'].append((start_local_clipped, end_local_clipped))

        temp_idx += 1

    return raw_periods, segment_idx


def _merge_sorted_periods(sorted_periods):
    if not sorted_periods:
        return []

    merged = []
    current_start, current_end = sorted_periods[0]

    for next_start, next_end in sorted_periods[1:]:
        if next_start <= current_end:
            current_end = max(current_end, next_end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = next_start, next_end

    merged.append((current_start, current_end))
    return merged


def _twilight_boundaries(twilight_periods):
    def get_overall_start_end(kind):
        periods = twilight_periods[kind]
        if not periods:
            return None, None
        all_dts = []
        for start_dt, end_dt in periods:
            all_dts.append(start_dt)
            all_dts.append(end_dt)
        return min(all_dts), max(all_dts)

    astro_start, astro_end = get_overall_start_end('astronomical')
    naut_start, naut_end = get_overall_start_end('nautical')
    civil_start, civil_end = get_overall_start_end('civil')
    return astro_start, astro_end, naut_start, naut_end, civil_start, civil_end


def _serialize_dt(dt):
    return dt.isoformat() if dt else None


def _serialize_periods(periods):
    if not periods:
        return []
    return [
        {'start': start.isoformat(), 'end': end.isoformat()}
        for start, end in periods
    ]


def _build_day_point(
    day_date,
    sunrise_dt,
    sunset_dt,
    transit_dt,
    twilight_periods,
    tz,
):
    if sunrise_dt and sunset_dt:
        length_hours = (sunset_dt - sunrise_dt).total_seconds() / 3600.0
        if length_hours < 0:
            length_hours += 24.0
    else:
        length_hours = None

    astro_start, astro_end, naut_start, naut_end, civil_start, civil_end = _twilight_boundaries(
        twilight_periods)

    return {
        "date": day_date.isoformat(),
        "sunrise": sunrise_dt.isoformat() if sunrise_dt else None,
        "sunset": sunset_dt.isoformat() if sunset_dt else None,
        "sunrise_hours": _to_hours(sunrise_dt),
        "sunset_hours": _to_hours(sunset_dt),
        "transit": transit_dt.isoformat() if transit_dt else None,
        "transit_hours": _to_hours(transit_dt),
        "day_length_hours": length_hours,
        "astronomical_twilight_start": _serialize_dt(astro_start),
        "astronomical_twilight_end": _serialize_dt(astro_end),
        "nautical_twilight_start": _serialize_dt(naut_start),
        "nautical_twilight_end": _serialize_dt(naut_end),
        "civil_twilight_start": _serialize_dt(civil_start),
        "civil_twilight_end": _serialize_dt(civil_end),
        "astronomical_twilight_periods": _serialize_periods(twilight_periods['astronomical']),
        "nautical_twilight_periods": _serialize_periods(twilight_periods['nautical']),
        "civil_twilight_periods": _serialize_periods(twilight_periods['civil']),
    }


def compute_sunpath_year(lat: float, lon: float, elevation: float, year: int) -> dict:
    """Compute sunrise and sunset times for each day of a year at a given location.

    Returns local times and day lengths, suitable for plotting a yearly curve.
    """
    tz = get_tzinfo(lat, lon)
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    sun = CELESTIAL_BODIES["sun"]

    f = almanac.risings_and_settings(eph, sun, location)
    twilight_f = almanac.dark_twilight_day(eph, location)

    points = []
    current = datetime(year, 1, 1)
    last = datetime(year + 1, 1, 1)

    start_utc_search = datetime(year, 1, 1, tzinfo=timezone.utc) - timedelta(days=2)
    end_utc_search = datetime(year + 1, 1, 1, tzinfo=timezone.utc) + timedelta(days=2)
    t_start = ts.from_datetime(start_utc_search)
    t_end = ts.from_datetime(end_utc_search)

    sun_times, sun_events = almanac.find_discrete(t_start, t_end, f)
    sun_events_by_date = _build_sun_events_by_date(sun_times, sun_events, tz)

    transit_func = almanac.meridian_transits(eph, sun, location)
    transit_times, transit_events = almanac.find_discrete(t_start, t_end, transit_func)
    transit_events_by_date = _build_transit_events_by_date(transit_times, transit_events, tz)

    has_twilight, all_segments = _build_twilight_segments(t_start, t_end, twilight_f)

    segment_idx = 0
    while current < last:
        lm = _local_midnight(current, tz)
        day_date = lm.date()

        day_events = sun_events_by_date.get(day_date, {})
        sunrise_dt = day_events.get('sunrise')
        sunset_dt = day_events.get('sunset')

        twilight_periods = {'astronomical': [], 'nautical': [], 'civil': []}
        if has_twilight:
            day_start_local = lm
            # The next local midnight, not lm + 24 h: DST days last 23 or 25 hours.
            day_end_local = _local_midnight(current + timedelta(days=1), tz)
            raw_periods, segment_idx = _collect_twilight_periods(
                day_start_local, day_end_local, all_segments, segment_idx, tz)

            for kind in twilight_periods:
                twilight_periods[kind] = _merge_sorted_periods(sorted(raw_periods[kind]))

        transit_dt = transit_events_by_date.get(day_date)

        points.append(_build_day_point(
            day_date, sunrise_dt, sunset_dt, transit_dt, twilight_periods, tz))

        current = current + timedelta(days=1)

    tz_name = getattr(tz, "zone", None) or str(tz)

    return {
        "version": SUNPATH_VERSION,
        "year": year,
        "location": {
            "latitude": lat,
            "longitude": lon,
            "elevation": elevation,
            "timezone": tz_name,
        },
        "points": points,
    }
