import uuid

import pytest

from app.agent.controller import AgentController, DuplicateTurn
from app.agent.state import Session, merge_preferences
from app.agent.tools import ToolValidationError, validate_tool_call
from app.inventory.location import location_store
from app.inventory.service import InventoryService
from app.providers.mock import MockLLMProvider
from app.schemas import Preferences
from app.services_settings import load_effective_config


async def make(db, **kw):
    cfg = await load_effective_config(db)
    return AgentController(db, cfg, MockLLMProvider(), **kw)


async def turn(ctrl, session, text):
    return await ctrl.handle_turn(session, str(uuid.uuid4()), text)


def test_merge_preferences_overrides_only_explicit():
    p = merge_preferences(Preferences(brand="Nike", color="red"), {"color": "blue", "size": None})
    assert p.brand == "Nike" and p.color == "blue" and p.size is None


def test_tool_validation_rejects_unknown_tool_and_bad_args():
    with pytest.raises(ToolValidationError):
        validate_tool_call("drop_tables", {})
    with pytest.raises(ToolValidationError):
        validate_tool_call("search_products", {"limit": 500})
    ok = validate_tool_call("search_products", {"brand": "Nike", "size": 9, "sort": "relevance", "limit": 5, "evil": "x"})
    assert ok.size == "9" and not hasattr(ok, "evil")  # T14: repaired/dropped safely


async def test_conversation_memory_flow(db):
    ctrl = await make(db)
    s = Session(session_id="s1", expires_at=9e12)
    r1 = await turn(ctrl, s, "I want red Nike shoes")
    assert r1.products and all(p.brand == "Nike" and p.primary_color == "red" for p in r1.products)  # T01
    assert r1.message.endswith("?")  # asks size
    r2 = await turn(ctrl, s, "size 9")
    assert s.preferences.size == "9" and s.preferences.brand == "Nike" and s.preferences.color == "red"  # T02
    assert all("9" in p.available_sizes for p in r2.products)
    prices_before = max(p.price for p in r2.products)
    r3 = await turn(ctrl, s, "show cheaper ones")
    assert r3.products and max(p.price for p in r3.products) < prices_before  # T03
    assert s.preferences.brand == "Nike" and s.preferences.color == "red"
    r4 = await turn(ctrl, s, "actually blue")
    assert s.preferences.color == "blue" and s.preferences.brand == "Nike"  # T04
    exact = [p for p in r4.products if not p.is_alternative]
    assert exact and all(p.primary_color == "blue" for p in exact)


async def test_exact_model_and_store_lookup(db):
    ctrl = await make(db)
    s = Session(session_id="s2", expires_at=9e12)
    r = await turn(ctrl, s, "Is MODEL-101 available?")
    assert r.products and r.products[0].model_id == "MODEL-101"  # T05
    r = await turn(ctrl, s, "Which nearest store has this in size 9?")
    assert "location" in r.message.lower() and r.stores is None  # T06/T07: asks for location, no nearest claim
    token, _ = location_store.issue(53.48, -2.24, "Manchester")
    s.location_token = token
    r = await turn(ctrl, s, "Which nearest store has this in size 9?")
    assert r.stores and r.stores[0].distance_km is not None
    assert r.stores == sorted(r.stores, key=lambda x: x.distance_km)
    assert "Manchester" in r.message


async def test_store_lookup_without_location_is_alphabetical(db):
    ctrl = await make(db)
    s = Session(session_id="s3", expires_at=9e12)
    await turn(ctrl, s, "Is MODEL-101 available?")
    r = await turn(ctrl, s, "which stores have this in size 9")
    assert r.stores and [x.name for x in r.stores] == sorted(x.name for x in r.stores)
    assert "nearest store" not in r.message.lower()  # no store labelled nearest without location


async def test_duplicate_turn_rejected(db):
    ctrl = await make(db)
    s = Session(session_id="s4", expires_at=9e12)
    await ctrl.handle_turn(s, "turn-1", "red shoes")
    with pytest.raises(DuplicateTurn):
        await ctrl.handle_turn(s, "turn-1", "red shoes")


async def test_inventory_outage_no_false_claims(db):
    ctrl = await make(db, inventory=InventoryService(db, fail=True))
    s = Session(session_id="s5", expires_at=9e12)
    r = await turn(ctrl, s, "red Nike shoes")
    assert "unavailable" in r.message.lower()
    assert all(p.stock_status == "unknown" for p in r.products)
