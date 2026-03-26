from __future__ import annotations

import copy
import json
import os
import re
import threading
import time as time_module
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from skyfield import almanac
from skyfield.api import Star, wgs84

from api.computation import ts, eph
from api.helpers import get_location_params, parse_time_param
from cache_utils import normalize_location, location_key
from data_paths import DATA_DIR
from timezone_utils import get_tzinfo

router = APIRouter()

CATALOG_URL = os.environ.get(
    "MESSIER_CATALOG_URL",
    "http://www.messier.seds.org/xtra/similar/dataRASC.txt",
)
CATALOG_PATH = DATA_DIR / "messier_catalog.txt"

_catalog_lock = threading.Lock()
_catalog = None
_catalog_by_id = None
_response_cache_lock = threading.Lock()
_response_cache = {}

MESSIER_CACHE_TTL_SECONDS = max(0, int(os.getenv("MESSIER_CACHE_TTL_SECONDS", "300")))
MESSIER_CACHE_BUCKET_MINUTES = max(1, int(os.getenv("MESSIER_CACHE_BUCKET_MINUTES", "5")))
MESSIER_CACHE_MAX_ENTRIES = max(16, int(os.getenv("MESSIER_CACHE_MAX_ENTRIES", "256")))

_TYPE_MAP = {
    "1": "Open Cluster",
    "2": "Globular Cluster",
    "3": "Planetary Nebula",
    "4": "Diffuse Nebula",
    "5": "Spiral Galaxy",
    "6": "Elliptical Galaxy",
    "7": "Irregular Galaxy",
    "8": "Lenticular Galaxy",
    "9": "Supernova Remnant",
    "A": "Asterism",
    "B": "Milky Way Patch",
    "C": "Binary Star",
}


def _ensure_catalog_downloaded(force: bool = False) -> None:
    """Download catalog to DATA_DIR if not present or forced."""
    if CATALOG_PATH.exists() and not force:
        return
    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = resp.read()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CATALOG_PATH, "wb") as f:
            f.write(data)
    except Exception as e:
        raise RuntimeError(f"Failed to download Messier catalog: {e}") from e


def _parse_ra_hours(entry: dict) -> Optional[float]:
    keys_hours = ["ra_hours", "ra_hour", "ra_h"]
    keys_deg = ["ra_deg", "ra_degrees", "ra"]
    for k in keys_hours:
        if k in entry:
            try:
                return float(entry[k])
            except Exception:
                continue
    for k in keys_deg:
        if k in entry:
            try:
                val = float(entry[k])
                return val if val <= 24 else val / 15.0
            except Exception:
                continue
    return None


def _parse_dec_deg(entry: dict) -> Optional[float]:
    for k in ["dec_deg", "dec", "decl", "dec_degrees"]:
        if k in entry:
            try:
                return float(entry[k])
            except Exception:
                continue
    return None


def _parse_ra_from_tokens(ra_h: str, ra_m: Optional[str]) -> Optional[float]:
    """Return RA in hours from separated tokens."""
    try:
        h = float(ra_h.replace(",", "."))
        m = float(ra_m.replace(",", ".")) if ra_m is not None else 0.0
        return h + m / 60.0
    except Exception:
        return None


def _parse_ra_compact(token: str) -> Optional[float]:
    """
    Handle compact RA formats like '09.55.8' (== 09h 55.8m) by splitting on dots/spaces.
    """
    try:
        parts = [p for p in re.split(r"[ .]+", token.strip()) if p]
        if len(parts) >= 2:
            h = float(parts[0].replace(",", "."))
            m = float(".".join(parts[1:]).replace(",", "."))
            return h + m / 60.0
        # Fallback: treat as decimal hours
        val = float(token.replace(",", "."))
        return val if val <= 24 else val / 15.0
    except Exception:
        return None


def _parse_dec(dec_deg_token: Optional[str], dec_min_token: Optional[str]) -> Optional[float]:
    if dec_deg_token is None:
        return None
    try:
        deg_val = float(dec_deg_token.replace(",", "."))
        sign = -1 if str(dec_deg_token).strip().startswith("-") else 1
        minutes = float(dec_min_token.replace(",", ".")) if dec_min_token is not None else 0.0
        return sign * (abs(deg_val) + minutes / 60.0)
    except Exception:
        return None


def _parse_rasc_text_catalog(raw_text: str) -> list:
    parsed = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("M"):
            continue
        tokens = stripped.split()
        if len(tokens) < 8:
            continue

        obj_id = tokens[0]
        type_code = tokens[3] if len(tokens) > 3 else ""
        type_str = _TYPE_MAP.get(type_code, type_code)

        if len(tokens) > 5 and tokens[5].startswith(("+", "-")):
            ra_hours = _parse_ra_compact(tokens[4])
            dec_deg_token = tokens[5] if len(tokens) > 5 else None
            dec_min_token = tokens[6] if len(tokens) > 6 else None
            mag_token_idx = 7
        else:
            ra_hours = _parse_ra_from_tokens(tokens[4], tokens[5] if len(tokens) > 5 else None)
            dec_deg_token = tokens[6] if len(tokens) > 6 else None
            dec_min_token = tokens[7] if len(tokens) > 7 else None
            mag_token_idx = 8

        dec_deg = _parse_dec(dec_deg_token, dec_min_token)

        mag = None
        if len(tokens) > mag_token_idx:
            try:
                mag = float(tokens[mag_token_idx].replace(",", "."))
            except Exception:
                mag = None

        if ra_hours is None or dec_deg is None:
            continue

        try:
            star = Star(ra_hours=ra_hours, dec_degrees=dec_deg)
        except Exception:
            continue

        parsed.append(
            {
                "id": obj_id,
                "name": obj_id,
                "type": type_str,
                "mag": mag,
                "ra_hours": ra_hours,
                "dec_deg": dec_deg,
                "star": star,
            }
        )
    return parsed


def _parse_json_catalog(raw: list) -> list:
    parsed = []
    for entry in raw or []:
        try:
            ra_hours = _parse_ra_hours(entry)
            dec_deg = _parse_dec_deg(entry)
            if ra_hours is None or dec_deg is None:
                continue
            star = Star(ra_hours=ra_hours, dec_degrees=dec_deg)
            obj_id = entry.get("id") or entry.get("messier") or entry.get("name") or entry.get("m")
            if obj_id and not str(obj_id).lower().startswith("m"):
                obj_id = f"M{obj_id}"
            name = entry.get("name") or obj_id or "Messier"
            obj_type = entry.get("type") or entry.get("object_type") or ""
            mag = entry.get("mag") or entry.get("magnitude") or entry.get("v_mag")
            mag = float(mag) if mag is not None else None
            parsed.append(
                {
                    "id": str(obj_id) if obj_id else name,
                    "name": name,
                    "type": obj_type,
                    "mag": mag,
                    "ra_hours": ra_hours,
                    "dec_deg": dec_deg,
                    "star": star,
                }
            )
        except Exception:
            continue
    return parsed


def _load_catalog() -> list:
    global _catalog, _catalog_by_id
    with _catalog_lock:
        if _catalog is not None:
            return _catalog

        _ensure_catalog_downloaded()
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                raw_json = json.loads(content)
                parsed = _parse_json_catalog(raw_json)
            except json.JSONDecodeError:
                parsed = _parse_rasc_text_catalog(content)
        except Exception as e:
            raise RuntimeError(f"Failed to read Messier catalog: {e}") from e

        _catalog = parsed
        _catalog_by_id = {str(item["id"]).strip().upper(): item for item in parsed if item.get("id")}
        return _catalog


def _get_catalog_object(object_id: Optional[str]) -> Optional[dict]:
    if not object_id:
        return None
    _load_catalog()
    try:
        return _catalog_by_id.get(str(object_id).strip().upper())
    except Exception:
        return None


def _time_bucket_utc_minutes(dt: datetime, bucket_minutes: int) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    bucket_seconds = max(60, int(bucket_minutes) * 60)
    floored_timestamp = int(dt_utc.timestamp()) // bucket_seconds * bucket_seconds
    bucket_dt = datetime.fromtimestamp(floored_timestamp, tz=timezone.utc)
    return bucket_dt.strftime("%Y%m%dT%H%M")


def _make_response_cache_key(
    lat: float,
    lon: float,
    elevation: float,
    dt_utc: datetime,
    details: bool,
    object_id: Optional[str],
) -> str:
    lat_n, lon_n, elev_n = normalize_location(lat, lon, elevation)
    loc_key = location_key(lat_n, lon_n, elev_n)
    time_key = _time_bucket_utc_minutes(dt_utc, MESSIER_CACHE_BUCKET_MINUTES)
    object_key = str(object_id).strip().upper() if object_id else "ALL"
    detail_key = "DETAILS" if details else "POSITIONS"
    return f"{loc_key}|{time_key}|{detail_key}|{object_key}"


def _cleanup_response_cache(now_mono: float) -> None:
    expired = [key for key, entry in _response_cache.items() if entry["expires_at"] <= now_mono]
    for key in expired:
        _response_cache.pop(key, None)

    while len(_response_cache) > MESSIER_CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_response_cache), None)
        if oldest_key is None:
            break
        _response_cache.pop(oldest_key, None)


def _get_cached_response(cache_key: str) -> Optional[dict]:
    if MESSIER_CACHE_TTL_SECONDS <= 0:
        return None

    now_mono = time_module.monotonic()
    with _response_cache_lock:
        entry = _response_cache.get(cache_key)
        if not entry:
            _cleanup_response_cache(now_mono)
            return None
        if entry["expires_at"] <= now_mono:
            _response_cache.pop(cache_key, None)
            _cleanup_response_cache(now_mono)
            return None
        return copy.deepcopy(entry["payload"])


def _store_cached_response(cache_key: str, payload: dict) -> None:
    if MESSIER_CACHE_TTL_SECONDS <= 0:
        return

    now_mono = time_module.monotonic()
    with _response_cache_lock:
        _cleanup_response_cache(now_mono)
        _response_cache[cache_key] = {
            "expires_at": now_mono + MESSIER_CACHE_TTL_SECONDS,
            "payload": copy.deepcopy(payload),
        }
        _cleanup_response_cache(now_mono)


def _compute_daily_events(observer, location, star, tz, dt_utc: datetime) -> tuple[Optional[str], Optional[str], Optional[str]]:
    rise_time = None
    set_time = None
    transit_time = None

    local_dt = dt_utc.astimezone(tz)
    local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(timezone.utc)
    start_time = ts.from_datetime(utc_midnight)
    end_time = ts.from_datetime(utc_midnight + timedelta(days=2))

    try:
        f = almanac.risings_and_settings(eph, star, location)
        times, events = almanac.find_discrete(start_time, end_time, f)
        for ti, ev in zip(times, events):
            ev_local = ti.utc_datetime().astimezone(tz)
            if ev_local.date() != local_dt.date():
                continue
            if ev == 1 and rise_time is None:
                rise_time = ev_local.isoformat()
            elif ev == 0 and set_time is None:
                set_time = ev_local.isoformat()

        transit_f = almanac.meridian_transits(eph, star, location)
        t_times, t_events = almanac.find_discrete(start_time, end_time, transit_f)
        best_transit = None
        best_alt = float("-inf")
        for ti, _ev in zip(t_times, t_events):
            ev_local = ti.utc_datetime().astimezone(tz)
            if ev_local.date() != local_dt.date():
                continue
            alt_deg = observer.at(ti).observe(star).apparent().altaz()[0].degrees
            if alt_deg > best_alt:
                best_alt = alt_deg
                best_transit = ev_local
        if best_transit:
            transit_time = best_transit.isoformat()
    except Exception:
        pass

    return rise_time, set_time, transit_time


@router.get("/messier")
async def get_messier_objects(
    request: Request,
    lat: float = None,
    lon: float = None,
    elevation: float = None,
    time: Optional[str] = None,
    object_id: Optional[str] = None,
    details: Optional[bool] = False,
    nocache: Optional[bool] = False,
):
    """Compute Messier object positions in real time (no precompute needed)."""
    try:
        lat, lon, elevation = get_location_params(request, lat, lon, elevation)
        dt_utc = parse_time_param(time)
        cache_key = None

        if not nocache:
            cache_key = _make_response_cache_key(lat, lon, elevation, dt_utc, bool(details), object_id)
            cached_payload = _get_cached_response(cache_key)
            if cached_payload is not None:
                return cached_payload

        catalog = _load_catalog()
        if not catalog:
            raise HTTPException(status_code=500, detail="Messier catalog is empty")

        tz = get_tzinfo(lat, lon)
        location = wgs84.latlon(lat, lon, elevation_m=elevation)
        observer = eph["earth"] + location
        t = ts.from_datetime(dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc))
        observer_at_t = observer.at(t)

        if object_id:
            selected = _get_catalog_object(object_id)
            if not selected:
                raise HTTPException(status_code=404, detail=f"Unknown Messier object: {object_id}")
            catalog = [selected]

        results = []
        for obj in catalog:
            try:
                star = obj["star"]
                app = observer_at_t.observe(star).apparent()
                alt, az, _ = app.altaz()
                payload = {
                    "id": obj["id"],
                    "name": obj["name"],
                    "type": obj.get("type"),
                    "magnitude": obj.get("mag"),
                    "ra": obj["ra_hours"] * 15.0,
                    "dec": obj["dec_deg"],
                    "altitude": alt.degrees,
                    "azimuth": az.degrees,
                    "symbol": "✦",
                }

                if details:
                    rise_time, set_time, transit_time = _compute_daily_events(observer, location, star, tz, dt_utc)
                    payload["rise_time"] = rise_time
                    payload["set_time"] = set_time
                    payload["transit_time"] = transit_time

                results.append(payload)
            except Exception:
                continue

        response_payload = {"objects": results, "catalog_size": len(catalog), "details": bool(details)}
        if cache_key is not None:
            _store_cached_response(cache_key, response_payload)
        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
