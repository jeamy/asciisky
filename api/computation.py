from datetime import datetime, timedelta, timezone
from skyfield import almanac
from skyfield.api import wgs84, Loader
from skyfield.magnitudelib import planetary_magnitude

from timezone_utils import get_tzinfo
from data_paths import DATA_DIR, DE421_PATH

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
                import math
                phase_factor = 0.5 * (1 - math.cos(moon_phase_angle))
                mag = -12.7 + 2.5 * math.log10(phase_factor) if phase_factor > 0 else -12.7
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
                    rise_dt = datetime.strptime(rise_time, '%H:%M').replace(year=local_dt.year, month=local_dt.month, day=local_dt.day, tzinfo=tz)
                    set_dt = datetime.strptime(set_time, '%H:%M').replace(year=local_dt.year, month=local_dt.month, day=local_dt.day, tzinfo=tz)
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
            print(f"Error calculating position for {name}: {str(e)}")
            continue

    return result

SUNPATH_VERSION = 2

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

    while current < last:
        lm = local_midnight(current)
        day_date = lm.date()

        # Use a 2-day window around this midnight to catch rise/set of that local day
        start_utc = lm.astimezone(timezone.utc)
        t0 = ts.from_datetime(start_utc)
        t1 = ts.from_datetime(start_utc + timedelta(days=2))

        sunrise_dt = None
        sunset_dt = None
        try:
            times, events = almanac.find_discrete(t0, t1, f)
            for ti, ev in zip(times, events):
                dt_local = ti.utc_datetime().astimezone(tz)
                if dt_local.date() != day_date:
                    continue
                if ev == 1 and sunrise_dt is None:
                    sunrise_dt = dt_local
                elif ev == 0 and sunset_dt is None:
                    sunset_dt = dt_local
        except Exception:
            sunrise_dt = None
            sunset_dt = None

        if sunrise_dt and sunset_dt:
            length_hours = (sunset_dt - sunrise_dt).total_seconds() / 3600.0
            if length_hours < 0:
                length_hours += 24.0
        else:
            length_hours = None

        # Twilight phases (astronomical, nautical, civil)
        twilight_periods = {
            'astronomical': [],
            'nautical': [],
            'civil': [],
        }

        try:
            # Build segments of twilight states over [t0, t1]
            state0 = int(twilight_f(t0))
            tw_times, tw_states = almanac.find_discrete(t0, t1, twilight_f)

            segments = []
            last_time = t0
            last_state = state0
            for ti, st in zip(tw_times, tw_states):
                seg_start_utc = last_time.utc_datetime()
                seg_end_utc = ti.utc_datetime()
                segments.append((seg_start_utc, seg_end_utc, int(last_state)))
                last_time = ti
                last_state = int(st)

            # Final segment to t1
            seg_start_utc = last_time.utc_datetime()
            seg_end_utc = t1.utc_datetime()
            segments.append((seg_start_utc, seg_end_utc, int(last_state)))

            day_start_local = lm
            day_end_local = lm + timedelta(days=1)

            # Collect all twilight segments for the current day
            raw_periods = {'astronomical': [], 'nautical': [], 'civil': []}
            for seg_start_utc, seg_end_utc, state in segments:
                seg_start_local = seg_start_utc.astimezone(tz)
                seg_end_local = seg_end_utc.astimezone(tz)
                start_local_clipped = max(seg_start_local, day_start_local)
                end_local_clipped = min(seg_end_local, day_end_local)

                if end_local_clipped > start_local_clipped:
                    if state == 2: # astronomical
                        raw_periods['astronomical'].append((start_local_clipped, end_local_clipped))
                    elif state == 3: # nautical
                        raw_periods['nautical'].append((start_local_clipped, end_local_clipped))
                    elif state == 4: # civil
                        raw_periods['civil'].append((start_local_clipped, end_local_clipped))

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

        except Exception:
            # Twilight information is optional; ignore errors
            astro_start = astro_end = naut_start = naut_end = civil_start = civil_end = None
            twilight_periods = {'astronomical': [], 'nautical': [], 'civil': []}

        def serialize_periods(kind):
            return [
                {'start': start.isoformat(), 'end': end.isoformat()}
                for start, end in twilight_periods.get(kind, [])
            ]

        def serialize_dt(dt):
            return dt.isoformat() if dt else None

        points.append({
            "date": day_date.isoformat(),
            "sunrise": sunrise_dt.isoformat() if sunrise_dt else None,
            "sunset": sunset_dt.isoformat() if sunset_dt else None,
            "sunrise_hours": to_hours(sunrise_dt),
            "sunset_hours": to_hours(sunset_dt),
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


def load_constellations():
    """
    Lädt Constellation-Daten aus Stellarium
    
    Diese Funktion wird vom Constellation Worker genutzt.
    Die eigentliche Berechnung erfolgt in api/routes/zodiac.py
    
    Returns:
        Dict mit Constellation-Metadaten
    """
    from api.routes.zodiac import CONSTELLATION_NAMES, CONSTELLATION_TRANSLATIONS
    
    # Gebe nur Metadaten zurück - die eigentliche Berechnung
    # erfolgt in zodiac.py mit Skyfield
    constellations = {}
    for name in CONSTELLATION_NAMES:
        constellations[name] = {
            'name': name,
            'name_de': CONSTELLATION_TRANSLATIONS.get(name, name)
        }
    
    return constellations
