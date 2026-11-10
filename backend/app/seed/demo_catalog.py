"""Deterministic fictional demo catalog.

All brands/models/stores here are fictional demo data (brand names are used only so natural
queries such as "red Nike shoes" work in the demo). Nothing represents real retail stock.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

DEMO_IMAGE_BASE = "/demo"  # served by the frontend's public folder

SIZES_STD = ["6", "7", "8", "9", "10", "11"]
SIZES_SMALL = ["5", "6", "7", "8", "9"]
SIZES_LARGE = ["8", "9", "10", "11", "12"]


@dataclass
class Colorway:
    code: str
    color: str                      # ground-truth primary color (used by fixture / vision mock)
    secondary: list[str] = field(default_factory=list)
    supplier_color: str | None = None  # color explicitly present in supplier text, if any
    broken_image: bool = False
    disagreement: bool = False      # supplier says one thing, vision says another -> needs review


@dataclass
class DemoProduct:
    model_id: str
    brand: str
    name: str
    description: str
    category: str
    style: str
    price: float
    sizes: list[str]
    colorways: list[Colorway]
    tags: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)


PRODUCTS: list[DemoProduct] = [
    DemoProduct("MODEL-101", "Nike", "Demo Air Runner 90", "Lightweight mesh upper with cushioned foam midsole. Demo product.", "running", "sneaker", 89.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color=None)], ["mesh", "cushioned"], ["running", "everyday"]),
    DemoProduct("MODEL-102", "Nike", "Demo Court Vision", "Classic court silhouette with padded collar. Available in two colorways.", "casual", "sneaker", 74.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color="red"), Colorway("BLUE", "blue", ["white"], supplier_color="blue")], ["leather look", "court"], ["casual", "everyday"]),
    DemoProduct("MODEL-103", "Nike", "Demo Pegasus Flow", "Responsive trainer for daily miles with breathable knit.", "running", "running shoe", 109.0, SIZES_STD,
                [Colorway("RED", "red", ["black"], supplier_color=None)], ["knit", "responsive"], ["running"]),
    DemoProduct("MODEL-104", "Nike", "Demo Metro Low", "Everyday low-top with suede overlays.", "casual", "sneaker", 65.0, SIZES_STD,
                [Colorway("BLK", "black", ["white"], supplier_color="black")], ["suede"], ["casual"]),
    DemoProduct("MODEL-105", "Nike", "Demo Street Crimson", "Bold street style with chunky outsole.", "casual", "chunky sneaker", 95.0, SIZES_STD,
                [Colorway("CRM", "red", ["grey"], supplier_color=None)], ["chunky"], ["casual", "street"]),
    DemoProduct("MODEL-106", "Adidas", "Demo Ultra Glide", "Energy-return midsole, sock-like fit.", "running", "running shoe", 120.0, SIZES_STD,
                [Colorway("RED", "red", ["black"], supplier_color="red")], ["energy return"], ["running"]),
    DemoProduct("MODEL-107", "Adidas", "Demo Campus Classic", "Heritage suede trainer with serrated stripes.", "casual", "sneaker", 70.0, SIZES_STD,
                [Colorway("GRN", "green", ["white"], supplier_color="green")], ["suede", "heritage"], ["casual"]),
    DemoProduct("MODEL-108", "Adidas", "Demo Terrex Trail", "Grippy trail outsole with reinforced toe cap.", "trail", "trail shoe", 99.0, SIZES_STD,
                [Colorway("BLK", "black", ["orange"], supplier_color="black")], ["trail", "grip"], ["hiking", "trail"]),
    DemoProduct("MODEL-109", "Puma", "Demo Velocity Nitro", "Nitrogen-infused foam for fast, light runs.", "running", "running shoe", 85.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color=None)], ["foam", "light"], ["running"]),
    DemoProduct("MODEL-110", "Puma", "Demo Suede Icon", "The iconic suede low-top.", "casual", "sneaker", 60.0, SIZES_STD,
                [Colorway("BUR", "burgundy", ["white"], supplier_color="burgundy", disagreement=True)], ["suede", "iconic"], ["casual"]),
    DemoProduct("MODEL-111", "New Balance", "Demo 574 Core", "Everyday comfort with ENCAP-style cushioning.", "casual", "sneaker", 80.0, SIZES_STD,
                [Colorway("GRY", "grey", ["white"], supplier_color="grey")], ["cushioned"], ["casual", "walking"]),
    DemoProduct("MODEL-112", "New Balance", "Demo Fresh Foam Walker", "Plush foam for all-day standing and walking.", "walking", "walking shoe", 95.0, SIZES_STD,
                [Colorway("BLK", "black", [], supplier_color="black"), Colorway("WHT", "white", ["grey"], supplier_color="white")], ["plush", "all-day"], ["walking", "standing", "work"]),
    DemoProduct("MODEL-113", "Asics", "Demo Gel Kayano", "Stability trainer with gel cushioning for long distances.", "running", "running shoe", 140.0, SIZES_STD,
                [Colorway("BLU", "blue", ["yellow"], supplier_color="blue")], ["stability", "gel"], ["running", "marathon"]),
    DemoProduct("MODEL-114", "Asics", "Demo Gel Contend", "Entry-level daily runner with gel heel.", "running", "running shoe", 55.0, SIZES_STD,
                [Colorway("RED", "red", ["black"], supplier_color=None)], ["gel", "value"], ["running", "gym"]),
    DemoProduct("MODEL-115", "Northway", "Demo Comfort Clog", "Slip-resistant clog built for long shifts; roomy toe box.", "work", "clog", 48.0, SIZES_STD,
                [Colorway("BLK", "black", [], supplier_color="black"), Colorway("NVY", "navy", [], supplier_color="navy")], ["slip-resistant", "roomy"], ["work", "standing", "nursing", "hospitality"]),
    DemoProduct("MODEL-116", "Northway", "Demo Shift Pro", "Cushioned work trainer with supportive insole for standing all day.", "work", "work trainer", 72.0, SIZES_STD,
                [Colorway("WHT", "white", ["grey"], supplier_color="white")], ["cushioned", "supportive insole"], ["work", "standing", "comfort"]),
    DemoProduct("MODEL-117", "Velora", "Demo Oxford Classic", "Polished leather oxford for formal occasions.", "formal", "oxford", 110.0, SIZES_LARGE,
                [Colorway("BLK", "black", [], supplier_color="black"), Colorway("BRN", "brown", [], supplier_color="brown")], ["leather", "polished"], ["formal", "office", "wedding"]),
    DemoProduct("MODEL-118", "Velora", "Demo Derby Brogue", "Brogued derby with rubber sole.", "formal", "derby", 98.0, SIZES_LARGE,
                [Colorway("TAN", "tan", [], supplier_color="tan")], ["brogue", "leather"], ["formal", "smart casual"]),
    DemoProduct("MODEL-119", "Velora", "Demo Loafer Soft", "Soft penny loafer in supple leather.", "formal", "loafer", 85.0, SIZES_STD,
                [Colorway("BUR", "burgundy", [], supplier_color="burgundy")], ["loafer", "soft leather"], ["smart casual", "office"]),
    DemoProduct("MODEL-120", "Saucony", "Demo Ride Daily", "Balanced daily trainer with a smooth ride.", "running", "running shoe", 105.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color="red")], ["balanced"], ["running"]),
    DemoProduct("MODEL-121", "Saucony", "Demo Peregrine Trail", "Aggressive lugs for soft ground.", "trail", "trail shoe", 115.0, SIZES_STD,
                [Colorway("GRN", "green", ["black"], supplier_color="green")], ["lugs", "trail"], ["trail", "hiking"]),
    DemoProduct("MODEL-122", "Brooks", "Demo Ghost Glide", "Soft, neutral everyday running shoe.", "running", "running shoe", 115.0, SIZES_STD,
                [Colorway("BLK", "black", ["white"], supplier_color="black")], ["neutral", "soft"], ["running", "walking"]),
    DemoProduct("MODEL-123", "Brooks", "Demo Addiction Walker", "Supportive walking shoe for long days on your feet.", "walking", "walking shoe", 100.0, SIZES_STD,
                [Colorway("WHT", "white", [], supplier_color="white")], ["supportive"], ["walking", "standing", "work"]),
    DemoProduct("MODEL-124", "Vans", "Demo Old School", "Canvas and suede skate shoe with side stripe.", "casual", "skate shoe", 58.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color=None), Colorway("BLK", "black", ["white"], supplier_color="black")], ["canvas", "skate"], ["casual", "skate"]),
    DemoProduct("MODEL-125", "Converse", "Demo All Court Hi", "Canvas high-top with vulcanised sole.", "casual", "high-top", 55.0, SIZES_STD,
                [Colorway("RED", "red", ["white"], supplier_color="red"), Colorway("WHT", "white", [], supplier_color="white")], ["canvas", "high-top"], ["casual"]),
    DemoProduct("MODEL-126", "Hoka", "Demo Clifton Cloud", "Maximal cushioning with a rockered sole.", "running", "running shoe", 130.0, SIZES_STD,
                [Colorway("ORG", "orange", ["white"], supplier_color=None)], ["max cushion", "rocker"], ["running", "walking", "standing"]),
    DemoProduct("MODEL-127", "Hoka", "Demo Bondi Max", "Our most cushioned road shoe for long hours on hard floors.", "running", "running shoe", 150.0, SIZES_STD,
                [Colorway("BLK", "black", [], supplier_color="black")], ["max cushion"], ["running", "standing", "work"]),
    DemoProduct("MODEL-128", "Skechers", "Demo Arch Fit Slip-in", "Hands-free slip-in with podiatrist-certified arch support.", "walking", "slip-on", 79.0, SIZES_STD,
                [Colorway("NVY", "navy", ["white"], supplier_color="navy"), Colorway("PNK", "pink", ["white"], supplier_color=None)], ["slip-in", "arch support"], ["walking", "standing", "comfort"]),
    DemoProduct("MODEL-129", "Dr. Martens", "Demo 1460 Boot", "8-eye leather boot with air-cushioned sole.", "boots", "boot", 159.0, SIZES_STD,
                [Colorway("BLK", "black", ["yellow"], supplier_color="black"), Colorway("CHR", "red", ["yellow"], supplier_color="cherry red")], ["leather", "boot"], ["casual", "winter"]),
    DemoProduct("MODEL-130", "Timberland", "Demo Yellow Boot", "Waterproof nubuck boot with padded collar.", "boots", "boot", 175.0, SIZES_LARGE,
                [Colorway("WHE", "yellow", ["brown"], supplier_color=None, broken_image=True)], ["waterproof", "nubuck"], ["outdoor", "winter"]),
    DemoProduct("MODEL-131", "Birkenstock", "Demo Arizona Sandal", "Two-strap sandal with contoured cork footbed.", "sandals", "sandal", 90.0, SIZES_STD,
                [Colorway("BRN", "brown", [], supplier_color="brown")], ["cork", "footbed"], ["summer", "casual"]),
    DemoProduct("MODEL-132", "Northway", "Demo Kids Flash", "Light-up kids trainer with hook-and-loop strap.", "kids", "sneaker", 35.0, SIZES_SMALL,
                [Colorway("RED", "red", ["blue"], supplier_color=None)], ["kids", "strap"], ["kids", "school"]),
    DemoProduct("MODEL-133", "Velora", "Demo Heeled Court", "Pointed court heel in patent finish.", "formal", "heel", 95.0, SIZES_SMALL,
                [Colorway("RED", "red", [], supplier_color="red"), Colorway("BLK", "black", [], supplier_color="black")], ["patent", "heel"], ["formal", "evening"]),
    DemoProduct("MODEL-134", "Nike", "Demo Flex Trainer", "Flexible gym trainer with grippy outsole.", "training", "training shoe", 68.0, SIZES_STD,
                [Colorway("PNK", "pink", ["white"], supplier_color="pink")], ["flexible", "gym"], ["gym", "training"]),
]

STORES = [
    {"name": "ShoeScout Oxford Street", "address": "200 Oxford Street", "city": "London", "postcode": "W1D 1NU", "latitude": 51.5155, "longitude": -0.1419},
    {"name": "ShoeScout Canary Wharf", "address": "Jubilee Place", "city": "London", "postcode": "E14 5NY", "latitude": 51.5033, "longitude": -0.0182},
    {"name": "ShoeScout Manchester Arndale", "address": "Market Street", "city": "Manchester", "postcode": "M4 3AQ", "latitude": 53.4839, "longitude": -2.2394},
    {"name": "ShoeScout Birmingham Bullring", "address": "Bullring", "city": "Birmingham", "postcode": "B5 4BU", "latitude": 52.4777, "longitude": -1.8944},
    {"name": "ShoeScout Leeds Trinity", "address": "Albion Street", "city": "Leeds", "postcode": "LS1 5AT", "latitude": 53.7971, "longitude": -1.5437},
]


def image_group_id(model_id: str, colorway: str) -> str:
    return f"{model_id}-{colorway}"


def image_url(model_id: str, cw: Colorway) -> str:
    if cw.broken_image:
        return "https://example.invalid/images/missing.jpg"
    return f"{DEMO_IMAGE_BASE}/{image_group_id(model_id, cw.code).lower()}.svg"


def content_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def deterministic_quantity(variant_sku: str, store_name: str) -> int:
    """Stable pseudo-random stock. Special cases exercise the PRD scenarios."""
    h = int(hashlib.sha256(f"{variant_sku}|{store_name}".encode()).hexdigest(), 16)
    # MODEL-108: size 9 out of stock everywhere, size 10 in stock.
    if variant_sku.startswith("SKU-MODEL-108-BLK-9"):
        return 0
    if variant_sku.startswith("SKU-MODEL-108-BLK-10"):
        return 3
    # Roughly 55% of (variant, store) pairs stocked.
    if h % 100 < 45:
        return 0
    return 1 + (h >> 8) % 6


def sku(model_id: str, cw_code: str, size: str) -> str:
    return f"SKU-{model_id}-{cw_code}-{size}"


def fixture_attributes() -> dict[str, dict]:
    """Offline attribute fixture (stands in for vision enrichment when no key is configured).

    Keyed by image_group_id. Marked source='fixture' so UI never claims a real provider produced it.
    """
    out: dict[str, dict] = {}
    for p in PRODUCTS:
        for cw in p.colorways:
            gid = image_group_id(p.model_id, cw.code)
            if cw.broken_image:
                continue  # broken image -> no fixture -> remains unknown until enrichment succeeds
            if cw.disagreement:
                # Supplier says burgundy; vision fixture says red. Preserve ambiguity.
                out[gid] = {
                    "primary_color": cw.supplier_color,
                    "secondary_colors": ["red"],
                    "style": p.style,
                    "category": p.category,
                    "tags": p.tags + p.use_cases,
                    "source": "fixture",
                    "review_status": "needs_review",
                    "evidence": {"supplier_color": cw.supplier_color, "vision_color": "red",
                                 "note": "supplier/vision disagreement; preserved supplier label"},
                }
                continue
            out[gid] = {
                "primary_color": cw.color,
                "secondary_colors": cw.secondary,
                "style": p.style,
                "category": p.category,
                "tags": p.tags + p.use_cases,
                "source": "supplier" if cw.supplier_color else "fixture",
                "review_status": "approved",
                "evidence": {"supplier_color": cw.supplier_color,
                             "vision_color": None if cw.supplier_color else cw.color},
            }
    return out


COLOR_HEX = {
    "red": "#D62828", "blue": "#2457C5", "black": "#1B1B1B", "white": "#F3F3F3", "grey": "#8C8C8C",
    "green": "#2E8B57", "burgundy": "#6E1423", "navy": "#1F2A5A", "brown": "#6B4226", "tan": "#C8A165",
    "orange": "#E8732A", "pink": "#E87BA6", "yellow": "#D9A400",
}
