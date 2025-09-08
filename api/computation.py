from datetime import datetime, timedelta, timezone
from skyfield import almanac
from skyfield.api import wgs84, Loader
from skyfield.magnitudelib import planetary_magnitude

from timezone_utils import get_tzinfo

# Load Skyfield data
LOADER = Loader('.')
ts = LOADER.timescale()
eph = LOADER('de421.bsp')

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
                start_time = ts.utc(dt_utc.replace(hour=0, minute=0, second=0, microsecond=0))
                end_time = ts.utc(start_time.utc_datetime() + timedelta(days=2))
                times, events = almanac.find_discrete(start_time, end_time, f)
                rise_time, set_time = None, None
                for ti, event in zip(times, events):
                    local_time_str = ti.utc_datetime().astimezone(tz).strftime('%H:%M')
                    if event == 1:
                        rise_time = local_time_str
                    else:
                        set_time = local_time_str

                transit_time = None
                if rise_time and set_time:
                    rise_dt = datetime.strptime(rise_time, '%H:%M').replace(year=dt_utc.year, month=dt_utc.month, day=dt_utc.day, tzinfo=tz)
                    set_dt = datetime.strptime(set_time, '%H:%M').replace(year=dt_utc.year, month=dt_utc.month, day=dt_utc.day, tzinfo=tz)
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
