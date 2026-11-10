"""Normalisation helpers shared by the router, mock NLU and ranking."""
from __future__ import annotations

import re

COLOR_SYNONYMS: dict[str, str] = {
    "red": "red", "crimson": "red", "scarlet": "red", "cherry": "red", "cherry red": "red",
    "blue": "blue", "royal blue": "blue", "sky blue": "blue",
    "navy": "navy", "dark blue": "navy",
    "black": "black", "white": "white", "cream": "white", "off-white": "white",
    "grey": "grey", "gray": "grey", "silver": "grey",
    "green": "green", "olive": "green",
    "burgundy": "burgundy", "maroon": "burgundy", "wine": "burgundy",
    "brown": "brown", "chocolate": "brown",
    "tan": "tan", "beige": "tan", "camel": "tan",
    "orange": "orange", "pink": "pink", "yellow": "yellow", "gold": "yellow", "purple": "purple",
}
COLORS = sorted(set(COLOR_SYNONYMS.values()))

CATEGORY_SYNONYMS: dict[str, str] = {
    "running": "running", "runner": "running", "runners": "running", "run": "running", "jogging": "running",
    "casual": "casual", "sneaker": "casual", "sneakers": "casual", "trainers": "casual", "trainer": "casual",
    "walking": "walking", "walk": "walking", "walker": "walking",
    "formal": "formal", "dress": "formal", "oxford": "formal", "oxfords": "formal", "brogue": "formal", "loafer": "formal",
    "loafers": "formal", "heels": "formal", "heel": "formal", "smart": "formal",
    "trail": "trail", "hiking": "trail", "hike": "trail",
    "work": "work", "clog": "work", "clogs": "work",
    "boots": "boots", "boot": "boots",
    "sandals": "sandals", "sandal": "sandals",
    "kids": "kids", "children": "kids", "child": "kids", "kid": "kids",
    "training": "training", "gym": "training", "workout": "training",
}

BRANDS = ["nike", "adidas", "puma", "new balance", "asics", "northway", "velora", "saucony", "brooks", "vans",
          "converse", "hoka", "skechers", "dr. martens", "dr martens", "doc martens", "timberland", "birkenstock"]
BRAND_CANON = {"dr martens": "Dr. Martens", "doc martens": "Dr. Martens", "dr. martens": "Dr. Martens",
               "new balance": "New Balance"}


def norm_color(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return COLOR_SYNONYMS.get(v, v if v in COLORS else None)


def norm_category(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    return CATEGORY_SYNONYMS.get(v, v if v in set(CATEGORY_SYNONYMS.values()) else None)


def norm_brand(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in BRAND_CANON:
        return BRAND_CANON[v]
    return v.title() if v in BRANDS else value.strip().title()


def norm_size(value: str | int | float | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper().replace("UK", "").replace("SIZE", "").strip()
    m = re.match(r"^(\d{1,2})(\.5)?$", s)
    if not m:
        return None
    return s if s.endswith(".5") else str(int(m.group(1)))


def norm_model_id(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"model[\s-]*(\d{3})", value, re.I)
    if m:
        return f"MODEL-{m.group(1)}"
    return None


STOPWORDS = {"the", "a", "an", "for", "to", "of", "in", "on", "and", "or", "with", "me", "i", "want", "need", "some",
             "shoe", "shoes", "pair", "something", "show", "find", "looking", "please", "that", "are", "is", "all", "day", "my"}


def stem(token: str) -> str:
    for suffix in ("able", "ing", "ers", "er", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in re.split(r"[^a-z0-9.]+", text.lower()) if t and t not in STOPWORDS]
