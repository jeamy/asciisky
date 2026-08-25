import math
from datetime import datetime, timedelta, timezone

from skyfield import almanac
from skyfield.api import Loader, wgs84
from skyfield.magnitudelib import planetary_magnitude

from data_paths import DATA_DIR
from timezone_utils import get_tzinfo

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


def _compute_body_position(body, observer, t):
    """Return apparent alt/az and Earth-center distance (au) for a body."""
    astrometric = observer.at(t).observe(body)
    apparent = astrometric.apparent()
    alt, az, _distance = apparent.altaz()

    earth_center = eph['earth'].at(t)
    earth_to_body = earth_center.observe(body)
    earth_distance = earth_to_body.distance().au

    return astrometric, alt, az, earth_distance


def _body_magnitude(name: str, astrometric, t) -> float:
    if name == 'sun':
        return _DEFAULT_MAGNITUDES['sun']

    if name == 'moon':
        moon_phase = almanac.moon_phase(eph, t)
        moon_phase_angle = float(moon_phase.radians)
        phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
        return moon_apparent_magnitude(phase_factor)

    if name in ('mercury', 'venus', 'mars', 'jupiter', 'saturn'):
        try:
            return planetary_magnitude(astrometric)
        except Exception:
            return _DEFAULT_MAGNITUDES.get(name, 0)

    return _DEFAULT_MAGNITUDES.get(name, 0)


def _localize_naive(naive_dt: datetime, timezone_obj):
    if hasattr(timezone_obj, 'localize'):
        return timezone_obj.localize(naive_dt)
    return naive_dt.replace(tzinfo=timezone_obj)


def _compute_transit_time(rise_time: str, set_time: str, tz, local_dt: datetime) -> str | None:
    rise_naive = datetime.strptime(rise_time, '%H:%M').replace(
        year=local_dt.year, month=local_dt.month, day=local_dt.day)
    set_naive = datetime.strptime(set_time, '%H:%M').replace(
        year=local_dt.year, month=local_dt.month, day=local_dt.day)
    rise_dt = _localize_naive(rise_naive, tz)
    set_dt = _localize_naive(set_naive, tz)
    if set_dt < rise_dt:
        set_dt += timedelta(days=1)
    transit_dt = rise_dt + (set_dt - rise_dt) / 2
    return transit_dt.strftime('%H:%M')


def _find_rise_set_transit(body, location, tz, dt_utc: datetime):
    """Return (rise_time, set_time, transit_time) as '%H:%M' strings or None."""
    f = almanac.risings_and_settings(eph, body, location)
    local_dt = dt_utc.astimezone(tz)
    local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(timezone.utc)
    start_time = ts.from_datetime(utc_midnight)
    end_time = ts.from_datetime(utc_midnight + timedelta(days=2))
    times, events = almanac.find_discrete(start_time, end_time, f)

    rise_time, set_time = None, None
    today_local = local_dt.date()

    for ti, event in zip(times, events):
        event_local = ti.utc_datetime().astimezone(tz)
        if event_local.date() == today_local:
            local_time_str = event_local.strftime('%H:%M')
            if event == 1 and rise_time is None:
                rise_time = local_time_str
            elif event == 0 and set_time is None:
                set_time = local_time_str

    transit_time = None
    if rise_time and set_time:
        transit_time = _compute_transit_time(rise_time, set_time, tz, local_dt)

    return rise_time, set_time, transit_time


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


def _add_moon_phase(body_entry: dict, astrometric, t) -> None:
    illumination = astrometric.fraction_illuminated(eph['sun'])
    phase_degrees = almanac.moon_phase(eph, t).degrees
    phase_name = ""
    if phase_degrees < 22.5 or phase_degrees >= 337.5:
        phase_name = "new_moon"
    elif phase_degrees < 67.5:
        phase_name = "waxing_crescent"
    elif phase_degrees < 112.5:
        phase_name = "first_quarter"
    elif phase_degrees < 177.5:
        phase_name = "waxing_gibbous"
    elif phase_degrees < 182.5:
        phase_name = "full_moon"
    elif phase_degrees < 247.5:
        phase_name = "waning_gibbous"
    elif phase_degrees < 292.5:
        phase_name = "last_quarter"
    else:
        phase_name = "waning_crescent"
    body_entry["phase"] = illumination
    body_entry["phase_name"] = phase_name


def compute_celestial_snapshot(lat: float, lon: float, elevation: float, dt_utc: datetime) -> dict:
    dt_utc = _ensure_utc(dt_utc)

    tz = get_tzinfo(lat, lon)
    t = ts.from_datetime(dt_utc)
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    observer = eph['earth'] + location

    result = {
        "time": dt_utc.isoformat(),
        "location": {"latitude": lat, "longitude": lon, "elevation": elevation},
        "bodies": {},
        "loading": False
    }

    for name, body in CELESTIAL_BODIES.items():
        try:
            astrometric, alt, az, earth_distance = _compute_body_position(body, observer, t)
            mag = _body_magnitude(name, astrometric, t)

            try:
                rise_time, set_time, transit_time = _find_rise_set_transit(body, location, tz, dt_utc)
            except Exception:
                rise_time, set_time, transit_time = None, None, None

            body_entry = _build_body_entry(
                name, alt, az, earth_distance, mag,
                rise_time, set_time, transit_time,
            )

            if name == 'moon':
                _add_moon_phase(body_entry, astrometric, t)

            result["bodies"][name] = body_entry
        except Exception as e:
            print(f"Error calculating position for {name}: {e!s}")
            continue

    return result


SUNPATH_VERSION = 5


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


def _build_transit_events_by_date(transit_times, transit_events, location, sun, tz):
    transit_events_by_date = {}
    for ti, ev in zip(transit_times, transit_events):
        try:
            dt_local = ti.utc_datetime().astimezone(tz)
            d = dt_local.date()
            alt_deg = (location.at(ti).observe(sun).apparent().altaz()[0].degrees)
            prev = transit_events_by_date.get(d)
            if prev is None or alt_deg > prev[1]:
                transit_events_by_date[d] = (dt_local, alt_deg, int(ev))
        except Exception:
            continue
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
    transit_events_by_date = _build_transit_events_by_date(
        transit_times, transit_events, location, sun, tz)

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
            day_end_local = lm + timedelta(days=1)
            raw_periods, segment_idx = _collect_twilight_periods(
                day_start_local, day_end_local, all_segments, segment_idx, tz)

            for kind in twilight_periods:
                twilight_periods[kind] = _merge_sorted_periods(sorted(raw_periods[kind]))

        transit_dt = None
        if day_date in transit_events_by_date:
            transit_dt = transit_events_by_date[day_date][0]

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
