import pytest

from app.inventory.service import InventoryService
from app.search.router import SearchRequest, choose_route, search_products


def test_route_selection():
    assert choose_route(SearchRequest(model="MODEL-101")) == "exact_model"
    assert choose_route(SearchRequest(brand="Nike", color="red")) == "attribute"
    assert choose_route(SearchRequest(use_case="comfortable for long shifts")) == "text"
    assert choose_route(SearchRequest(model="Air Runner")) == "model_text"


async def test_red_nike_returns_in_stock_red_only(db):
    res = await search_products(db, SearchRequest(brand="Nike", color="red"))
    assert res.route == "attribute"
    assert 3 <= len(res.products) <= 5
    assert all(p.brand == "Nike" and p.primary_color == "red" and p.in_stock for p in res.products)
    assert all(not p.is_alternative for p in res.products)


async def test_two_colorways_separate_groups(db):
    red = await search_products(db, SearchRequest(model="MODEL-102", color="red"))
    blue = await search_products(db, SearchRequest(model="MODEL-102", color="blue"))
    assert red.products[0].primary_color == "red" and blue.products[0].primary_color == "blue"
    assert red.products[0].image_group_id != blue.products[0].image_group_id  # T18


async def test_exact_model_route_no_text_search(db):
    res = await search_products(db, SearchRequest(model="MODEL-101"))
    assert res.route == "exact_model"
    assert res.products and res.products[0].model_id == "MODEL-101"


async def test_size_unavailable_gives_labeled_alternative(db):
    res = await search_products(db, SearchRequest(model="MODEL-108", size="9"))
    assert res.products, "should offer alternatives"
    assert all(p.is_alternative and "size" in p.relaxed for p in res.products)  # T08
    assert "9" not in res.products[0].available_sizes and "10" in res.products[0].available_sizes


async def test_price_filter(db):
    res = await search_products(db, SearchRequest(color="red", max_price=60))
    assert res.products
    for p in res.products:
        if not p.is_alternative:
            assert p.price <= 60


async def test_use_case_text_route(db):
    res = await search_products(db, SearchRequest(use_case="comfortable shoes for standing all day"))
    assert res.route == "text"
    assert res.products
    assert any("standing" in str(p.name).lower() or p.category in ("work", "walking", "running") for p in res.products)


async def test_inventory_failure_yields_unknown_not_in_stock(db):
    res = await search_products(db, SearchRequest(brand="Nike", color="red"), inventory=InventoryService(db, fail=True))
    assert res.inventory_status == "unavailable"
    assert res.products and all(p.stock_status == "unknown" and not p.in_stock for p in res.products)  # T13


async def test_needs_review_color_not_asserted(db):
    # MODEL-110 supplier says burgundy, vision fixture says red -> flagged, primary stays burgundy, red only secondary
    res = await search_products(db, SearchRequest(brand="Puma", color="red"))
    for p in res.products:
        if p.model_id == "MODEL-110":
            assert p.primary_color == "burgundy" and p.color_confidence != "verified"
