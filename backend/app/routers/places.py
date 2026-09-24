"""Place search through OpenStreetMap's Nominatim service (https://operations.osmfoundation.org/policies/nominatim/)."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException

from app.auth import CurrentUser

GEOCODER_URL = os.environ.get("TRACEPAI_GEOCODER_URL", "https://nominatim.openstreetmap.org").rstrip("/")
USER_AGENT = "TracepAI/1.0 (self-hosted personal finance app)"

router = APIRouter(prefix="/places", tags=["places"])


def _get(path: str, params: dict):
    url = f"{GEOCODER_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError):
        raise HTTPException(503, "Place search is unavailable right now. Check the internet connection and try again.")


def _place(item: dict) -> dict:
    address = item.get("display_name", "")
    return {
        "name": item.get("name") or address.split(",")[0],
        "address": address,
        "lat": float(item["lat"]),
        "lng": float(item["lon"]),
    }


@router.get("/search")
def search(q: str, user: CurrentUser):
    if not q.strip():
        return []
    return [_place(item) for item in _get("/search", {"q": q, "format": "jsonv2", "limit": 5})]


@router.get("/reverse")
def reverse(lat: float, lng: float, user: CurrentUser):
    item = _get("/reverse", {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 18})
    return _place(item) if "lat" in item else {"name": "", "address": "", "lat": lat, "lng": lng}
