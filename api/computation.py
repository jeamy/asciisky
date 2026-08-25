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


def moon_apparent_magnitude(phase_factor: float) -> float:
    """Return a finite, continuous apparent magnitude for the Moon."""
    return -12.7 - 2.5 * math.log10(max(float(phase_factor), 1e-6))

def compute_celestial_snapshot(lat: float, lon: float, elevation: float, dt_utc: datetime) -> dict:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

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
            astrometric = observer.at(t).observe(body)
            apparent = astrometric.apparent()
            alt, az, distance = apparent.altaz()

            earth_center = eph['earth'].at(t)
            earth_to_body = earth_center.observe(body)
            earth_distance = earth_to_body.distance().au

            if name == 'sun':
                mag = -26.74
            elif name == 'moon':
                moon_phase = almanac.moon_phase(eph, t)
                moon_phase_angle = float(moon_phase.radians)
                phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
                # At full moon the apparent magnitude is about -12.7.  A
                # smaller illuminated fraction must be dimmer (larger
                # magnitude), including exactly at new moon.  The floor keeps
                # the logarithm finite without introducing a discontinuity.
                mag = moon_apparent_magnitude(phase_factor)
            elif name in ['mercury', 'venus', 'mars', 'jupiter', 'saturn']:
                try:
                    mag = planetary_magnitude(astrometric)
                except Exception:
                    mag = {
                        'mercury': 0.23, 'venus': -4.14, 'mars': 1.66,
                        'jupiter': -2.2, 'saturn': 0.46
                    }.get(name, 0)
            else:
                mag = {'uranus': 5.7, 'neptune': 7.8}.get(name, 0)

            try:
                f = almanac.risings_and_settings(eph, body, location)
                # Use local midnight as reference point, not UTC midnight
                local_dt = dt_utc.astimezone(tz)
                local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                # Convert back to UTC for Skyfield
                utc_midnight = local_midnight.astimezone(timezone.utc)
                start_time = ts.from_datetime(utc_midnight)
                end_time = ts.from_datetime(utc_midnight + timedelta(days=2))
                times, events = almanac.find_discrete(start_time, end_time, f)
                
                # Find rise/set events for the current local day
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
                    def _localize(naive_dt, timezone_obj):
                        if hasattr(timezone_obj, 'localize'):
                            return timezone_obj.localize(naive_dt)
                        return naive_dt.replace(tzinfo=timezone_obj)
                    rise_naive = datetime.strptime(rise_time, '%H:%M').replace(
                        year=local_dt.year, month=local_dt.month, day=local_dt.day)
                    set_naive = datetime.strptime(set_time, '%H:%M').replace(
                        year=local_dt.year, month=local_dt.month, day=local_dt.day)
                    rise_dt = _localize(rise_naive, tz)
                    set_dt = _localize(set_naive, tz)
                    if set_dt < rise_dt:
                        set_dt += timedelta(days=1)
                    transit_dt = rise_dt + (set_dt - rise_dt) / 2
                    transit_time = transit_dt.strftime('%H:%M')
            except Exception:
                rise_time, set_time, transit_time = None, None, None

            body_entry = {
                "name": name, "symbol": BODY_SYMBOLS.get(name, "?"),
                "altitude": float(alt.degrees), "azimuth": float(az.degrees),
                "distance": float(earth_distance), "magnitude": float(mag),
                "visible": True, "transit_time": transit_time,
                "rise_time": rise_time, "set_time": set_time
            }

            if name == 'moon':
                illumination = astrometric.fraction_illuminated(eph['sun'])
                phase_degrees = almanac.moon_phase(eph, t).degrees
                phase_name = ""
                if phase_degrees < 22.5 or phase_degrees >= 337.5: phase_name = "new_moon"
                elif phase_degrees < 67.5: phase_name = "waxing_crescent"
                elif phase_degrees < 112.5: phase_name = "first_quarter"
                elif phase_degrees < 177.5: phase_name = "waxing_gibbous"
                elif phase_degrees < 182.5: phase_name = "full_moon"
                elif phase_degrees < 247.5: phase_name = "waning_gibbous"
                elif phase_degrees < 292.5: phase_name = "last_quarter"
                else: phase_name = "waning_crescent"
                body_entry["phase"] = illumination
                body_entry["phase_name"] = phase_name

            result["bodies"][name] = body_entry
        except Exception as e:
            print(f"Error calculating position for {name}: {e!s}")
            continue

    return result

SUNPATH_VERSION = 5

def compute_sunpath_year(lat: float, lon: float, elevation: float, year: int) -> dict:
    """Compute sunrise and sunset times for each day of a year at a given location.

    Returns local times and day lengths, suitable for plotting a yearly curve.
    """
    tz = get_tzinfo(lat, lon)
    location = wgs84.latlon(lat, lon, elevation_m=elevation)
    sun = CELESTIAL_BODIES["sun"]

    # Build functions once, reuse for each day
    f = almanac.risings_and_settings(eph, sun, location)
    # dark_twilight_day only needs ephemeris and observer (location)
    twilight_f = almanac.dark_twilight_day(eph, location)

    def local_midnight(day: datetime) -> datetime:
        """Return local midnight for given date, handling pytz and stdlib timezones."""
        naive = datetime(day.year, day.month, day.day)
        try:
            # pytz-style API
            if hasattr(tz, "localize"):
                return tz.localize(naive)
        except Exception:
            pass
        # Fallback: attach tzinfo directly
        return naive.replace(tzinfo=tz)

    def to_hours(dt) -> float | None:
        if dt is None:
            return None
        return dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    points = []
    current = datetime(year, 1, 1)
    last = datetime(year + 1, 1, 1)

    # Pre-calculate all events for the year to avoid repeated Skyfield calls
    # Add a buffer to ensure we cover all local times for the requested year
    start_utc_search = datetime(year, 1, 1, tzinfo=timezone.utc) - timedelta(days=2)
    end_utc_search = datetime(year + 1, 1, 1, tzinfo=timezone.utc) + timedelta(days=2)
    t_start = ts.from_datetime(start_utc_search)
    t_end = ts.from_datetime(end_utc_search)

    # 1. Sunrise and Sunset
    sun_times, sun_events = almanac.find_discrete(t_start, t_end, f)
    
    sun_events_by_date = {}
    for ti, ev in zip(sun_times, sun_events):
        dt_local = ti.utc_datetime().astimezone(tz)
        d = dt_local.date()
        if d not in sun_events_by_date:
            sun_events_by_date[d] = {'sunrise': None, 'sunset': None}
        
        # ev=1 is rise, ev=0 is set
        if ev == 1 and sun_events_by_date[d]['sunrise'] is None:
            sun_events_by_date[d]['sunrise'] = dt_local
        elif ev == 0 and sun_events_by_date[d]['sunset'] is None:
            sun_events_by_date[d]['sunset'] = dt_local

    # 1b. Meridian transits (solar noon / highest point)
    transit_func = almanac.meridian_transits(eph, sun, location)
    transit_times, transit_events = almanac.find_discrete(t_start, t_end, transit_func)
    transit_events_by_date = {}
    for ti, ev in zip(transit_times, transit_events):
        try:
            dt_local = ti.utc_datetime().astimezone(tz)
            d = dt_local.date()
            # Upper transit = highest culmination; Skyfield uses event=1 for upper
            # But select the event with maximum altitude per day for safety.
            alt_deg = (location.at(ti).observe(sun).apparent().altaz()[0].degrees)
            prev = transit_events_by_date.get(d)
            if prev is None or alt_deg > prev[1]:
                transit_events_by_date[d] = (dt_local, alt_deg, int(ev))
        except Exception:
            continue

    # 2. Twilight
    # Calculate all twilight transitions for the year
    try:
        tw_times, tw_states = almanac.find_discrete(t_start, t_end, twilight_f)
        initial_state = int(twilight_f(t_start))
        
        # Build a flat list of all segments: (start_utc, end_utc, state)
        all_segments = []
        last_time_utc = start_utc_search
        last_state = initial_state
        
        for ti, st in zip(tw_times, tw_states):
            ti_utc = ti.utc_datetime()
            all_segments.append((last_time_utc, ti_utc, last_state))
            last_time_utc = ti_utc
            last_state = int(st)
        all_segments.append((last_time_utc, end_utc_search, last_state))
        
        has_twilight = True
    except Exception:
        has_twilight = False
        all_segments = []

    # Iterate through each day of the year
    segment_idx = 0
    num_segments = len(all_segments)
    
    while current < last:
        lm = local_midnight(current)
        day_date = lm.date()
        
        # Sunrise/Sunset
        day_events = sun_events_by_date.get(day_date, {})
        sunrise_dt = day_events.get('sunrise')
        sunset_dt = day_events.get('sunset')

        if sunrise_dt and sunset_dt:
            length_hours = (sunset_dt - sunrise_dt).total_seconds() / 3600.0
            if length_hours < 0:
                length_hours += 24.0
        else:
            length_hours = None

        # Twilight
        twilight_periods = {
            'astronomical': [],
            'nautical': [],
            'civil': [],
        }
        
        astro_start = astro_end = naut_start = naut_end = civil_start = civil_end = None

        if has_twilight:
            day_start_local = lm
            day_end_local = lm + timedelta(days=1)
            
            # Find segments that overlap with this day
            # Since we iterate days sequentially, we can advance segment_idx
            # But we must be careful not to advance past segments that might overlap the NEXT day 
            # (though segments are contiguous, so a segment overlapping end of today overlaps start of tomorrow)
            # Actually, we just need to find the first segment that ends after day_start_local
            
            # Advance index to the first relevant segment
            # We compare segment end time (converted to local) with day_start_local
            while segment_idx < num_segments:
                seg_end_utc = all_segments[segment_idx][1]
                if seg_end_utc.astimezone(tz) > day_start_local:
                    break
                segment_idx += 1
            
            # Collect segments for this day
            # We scan forward from segment_idx until we find a segment that starts after day_end_local
            temp_idx = segment_idx
            raw_periods = {'astronomical': [], 'nautical': [], 'civil': []}
            
            while temp_idx < num_segments:
                seg_start_utc, seg_end_utc, state = all_segments[temp_idx]
                seg_start_local = seg_start_utc.astimezone(tz)
                
                if seg_start_local >= day_end_local:
                    break
                
                seg_end_local = seg_end_utc.astimezone(tz)
                start_local_clipped = max(seg_start_local, day_start_local)
                end_local_clipped = min(seg_end_local, day_end_local)

                if end_local_clipped > start_local_clipped:
                    if state == 1:  # astronomical
                        raw_periods['astronomical'].append((start_local_clipped, end_local_clipped))
                    elif state == 2:  # nautical
                        raw_periods['nautical'].append((start_local_clipped, end_local_clipped))
                    elif state == 3:  # civil
                        raw_periods['civil'].append((start_local_clipped, end_local_clipped))
                
                temp_idx += 1

            # Merge overlapping/adjacent segments for each twilight type
            for kind in twilight_periods:
                sorted_periods = sorted(raw_periods[kind])
                if not sorted_periods:
                    continue

                merged = []
                current_start, current_end = sorted_periods[0]

                for next_start, next_end in sorted_periods[1:]:
                    if next_start <= current_end:
                        current_end = max(current_end, next_end)
                    else:
                        merged.append((current_start, current_end))
                        current_start, current_end = next_start, next_end

                merged.append((current_start, current_end))
                twilight_periods[kind] = merged

            # Extract overall start/end times from the merged periods
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

        def serialize_periods(kind):
            periods = twilight_periods.get(kind, [])
            if not periods:
                return []

            return [
                {'start': start.isoformat(), 'end': end.isoformat()}
                for start, end in periods
            ]

        def serialize_dt(dt):
            return dt.isoformat() if dt else None

        transit_dt = None
        if day_date in transit_events_by_date:
            transit_dt = transit_events_by_date[day_date][0]

        points.append({
            "date": day_date.isoformat(),
            "sunrise": sunrise_dt.isoformat() if sunrise_dt else None,
            "sunset": sunset_dt.isoformat() if sunset_dt else None,
            "sunrise_hours": to_hours(sunrise_dt),
            "sunset_hours": to_hours(sunset_dt),
            "transit": transit_dt.isoformat() if transit_dt else None,
            "transit_hours": to_hours(transit_dt),
            "day_length_hours": length_hours,
            "astronomical_twilight_start": serialize_dt(astro_start),
            "astronomical_twilight_end": serialize_dt(astro_end),
            "nautical_twilight_start": serialize_dt(naut_start),
            "nautical_twilight_end": serialize_dt(naut_end),
            "civil_twilight_start": serialize_dt(civil_start),
            "civil_twilight_end": serialize_dt(civil_end),
            "astronomical_twilight_periods": serialize_periods('astronomical'),
            "nautical_twilight_periods": serialize_periods('nautical'),
            "civil_twilight_periods": serialize_periods('civil'),
        })

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
