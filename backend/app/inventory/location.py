"""Opaque, short-lived location tokens. Precise coordinates never enter LLM prompts."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from ..config import get_settings

# Fictional demo geocoder for UK postcodes/cities (production: real geocoding service).
CITY_COORDS = {
    "london": (51.5074, -0.1278), "manchester": (53.4808, -2.2426), "birmingham": (52.4862, -1.8904),
    "leeds": (53.8008, -1.5491), "liverpool": (53.4084, -2.9916), "bristol": (51.4545, -2.5879),
    "edinburgh": (55.9533, -3.1883), "glasgow": (55.8642, -4.2518), "sheffield": (53.3811, -1.4701),
}
POSTCODE_AREAS = {"W": "london", "E": "london", "N": "london", "SW": "london", "SE": "london", "NW": "london", "EC": "london",
                  "WC": "london", "M": "manchester", "B": "birmingham", "LS": "leeds", "L": "liverpool", "BS": "bristol",
                  "EH": "edinburgh", "G": "glasgow", "S": "sheffield"}


@dataclass
class LocationRecord:
    lat: float
    lon: float
    label: str
    expires_at: float


class LocationStore:
    def __init__(self) -> None:
        self._items: dict[str, LocationRecord] = {}

    def issue(self, lat: float, lon: float, label: str) -> tuple[str, float]:
        self._gc()
        token = "loc_" + secrets.token_urlsafe(16)
        exp = time.time() + get_settings().location_token_ttl_seconds
        self._items[token] = LocationRecord(lat=lat, lon=lon, label=label, expires_at=exp)
        return token, exp

    def resolve(self, token: str | None) -> LocationRecord | None:
        if not token:
            return None
        rec = self._items.get(token)
        if rec and rec.expires_at > time.time():
            return rec
        return None

    def _gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self._items.items() if v.expires_at <= now]:
            del self._items[k]


def geocode(postcode: str | None, city: str | None) -> tuple[float, float, str] | None:
    if city and city.strip().lower() in CITY_COORDS:
        lat, lon = CITY_COORDS[city.strip().lower()]
        return lat, lon, city.strip().title()
    if postcode:
        pc = postcode.strip().upper().replace(" ", "")
        area = "".join(ch for ch in pc[:2] if ch.isalpha())
        for key in (area, area[:1]):
            if key in POSTCODE_AREAS:
                lat, lon = CITY_COORDS[POSTCODE_AREAS[key]]
                return lat, lon, f"near {postcode.strip().upper()}"
    return None


location_store = LocationStore()
