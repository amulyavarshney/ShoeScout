"""Custom agent controller: one bounded tool loop shared by typed and voice turns."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..inventory.location import location_store
from ..inventory.service import InventoryService, InventoryUnavailable
from ..providers.base import AgentRequest, ProviderError, ToolCall
from ..schemas import ProductCard, StoreAvailability
from ..search.index import get_search_backend
from ..search.normalize import norm_color, norm_size
from ..search.router import SearchRequest, search_products
from ..services_settings import EffectiveConfig
from .prompt import build_system_prompt
from .state import Session, merge_preferences
from .tools import TOOLS, ToolValidationError, validate_tool_call

log = logging.getLogger("shoescout.agent")
MAX_TOOL_ROUNDS = 3
EventSink = Callable[[dict], Awaitable[None]]


@dataclass
class TurnOutcome:
    turn_id: str
    message: str
    products: list[ProductCard] = field(default_factory=list)
    stores: list[StoreAvailability] | None = None
    state: str = "complete"
    relaxed_constraints: list[str] = field(default_factory=list)
    timings: dict = field(default_factory=dict)


class DuplicateTurn(Exception):
    pass


async def _noop(_: dict) -> None:
    return None


class AgentController:
    def __init__(self, db: AsyncSession, cfg: EffectiveConfig, llm, *, inventory: InventoryService | None = None) -> None:
        self.db = db
        self.cfg = cfg
        self.llm = llm
        self.inventory = inventory or InventoryService(db)
        self._last_context_reset: list[str] = []

    async def handle_turn(self, session: Session, turn_id: str, transcript: str, *, emit: EventSink = _noop) -> TurnOutcome:
        if turn_id in session.processed_turns or session.active_turn == turn_id:
            raise DuplicateTurn(turn_id)
        session.active_turn = turn_id
        session.config_version = self.cfg.config_version
        t0 = time.perf_counter()
        timings: dict = {}
        transcript = transcript.strip()
        session.add_message("user", transcript)
        products: list[ProductCard] = []
        stores: list[StoreAvailability] | None = None
        relaxed: list[str] = []
        state = "complete"
        tool_results: list[tuple[ToolCall, dict]] = []
        previous_response_id: str | None = None
        try:
            request = AgentRequest(system_prompt=self._system_prompt(session), messages=list(session.recent_messages),
                                   tools=TOOLS, model=self.cfg.llm_model, context=self._context(session))
            final_text: str | None = None
            for _round in range(MAX_TOOL_ROUNDS):
                await emit({"type": "agent.state", "turn_id": turn_id, "state": "thinking"})
                t = time.perf_counter()
                result = await self.llm.respond(request)
                timings[f"llm_round_{_round}"] = round((time.perf_counter() - t) * 1000)
                previous_response_id = result.response_id
                if result.is_final:
                    final_text = result.text or "I couldn't find anything for that. Could you rephrase?"
                    break
                await emit({"type": "agent.state", "turn_id": turn_id, "state": "searching"})
                self._last_context_reset = list(request.context.get("reset_keys") or [])
                for call in result.tool_calls:
                    t = time.perf_counter()
                    payload = await self._execute(call, session)
                    timings[f"tool_{call.name}"] = round((time.perf_counter() - t) * 1000)
                    await emit({"type": "tool.called", "turn_id": turn_id, "name": call.name})
                    tool_results.append((call, payload))
                    if call.name == "search_products" and "products" in payload:
                        products = [ProductCard(**p) for p in payload["products"]]
                        relaxed = payload.get("relaxed_constraints", [])
                        await emit({"type": "search.results", "turn_id": turn_id, "products": payload["products"],
                                    "relaxed_constraints": relaxed, "inventory_status": payload.get("inventory_status", "ok")})
                    if call.name == "get_store_availability" and "stores" in payload:
                        stores = [StoreAvailability(**s) for s in payload["stores"]]
                        await emit({"type": "store.results", "turn_id": turn_id, "stores": payload["stores"],
                                    "variant_id": payload.get("variant_id"), "size": payload.get("size"),
                                    "location_known": payload.get("location_known", False),
                                    "inventory_status": payload.get("inventory_status", "ok")})
                request = AgentRequest(system_prompt=request.system_prompt, messages=request.messages, tools=TOOLS,
                                       tool_results=tool_results, previous_response_id=previous_response_id,
                                       model=self.cfg.llm_model, context=self._context(session))
            if final_text is None:
                final_text = "I couldn't finish that search. Please try again."
                state = "error"
            final_text = self._ground(final_text, products, stores)
        except ProviderError as e:
            log.warning("provider error turn=%s code=%s", turn_id, e.code)
            final_text = "I'm having trouble reaching the assistant right now. You can still search by typing a brand, colour or style."
            state = "error"
        finally:
            session.active_turn = None
        if state != "error" and products:
            session.last_results = [{"variant_id": p.variant_id, "name": p.name, "price": p.price, "currency": p.currency,
                                     "product_id": p.product_id} for p in products]
        if final_text.rstrip().endswith("?") and state == "complete":
            state = "needs_clarification"
        session.add_message("assistant", final_text)
        session.processed_turns = (session.processed_turns + [turn_id])[-50:]
        timings["total"] = round((time.perf_counter() - t0) * 1000)
        return TurnOutcome(turn_id=turn_id, message=final_text, products=products, stores=stores, state=state,
                           relaxed_constraints=relaxed, timings=timings)

    # ---- helpers ----
    def _context(self, session: Session) -> dict:
        return {"preferences": session.preferences.model_dump(), "selected_variant_id": session.selected_variant_id,
                "last_results": session.last_results, "location_token": session.location_token, "currency": self.cfg.currency}

    def _system_prompt(self, session: Session) -> str:
        return build_system_prompt(session.preferences.model_dump(), session.selected_variant_id, session.last_results,
                                   session.language, self.cfg.currency, bool(location_store.resolve(session.location_token)))

    async def _execute(self, call: ToolCall, session: Session) -> dict:
        try:
            args = validate_tool_call(call.name, call.arguments)
        except ToolValidationError as e:
            log.warning("rejected tool call %s: %s", call.name, e)
            return {"error": "INVALID_TOOL_ARGUMENTS", "message": "Tool arguments were invalid and were not executed."}
        if call.name == "search_products":
            a = args.model_dump()
            # Topic shift: a new model ID (or an explicit reset from the planner) drops earlier attribute filters.
            reset_keys = list(self._last_context_reset or [])
            if a.get("model") and session.preferences.model and a["model"] != session.preferences.model:
                reset_keys += ["brand", "color", "category", "use_case", "max_price"]
            for k in set(reset_keys):
                setattr(session.preferences, k, None)
            # Preference memory: validated merge (explicit values override).
            session.preferences = merge_preferences(session.preferences, {k: a.get(k) for k in ("brand", "model", "color", "category", "size", "max_price", "use_case")})
            if a.get("color") and norm_color(a["color"]) and session.preferences.color != norm_color(a["color"]):
                session.preferences.color = norm_color(a["color"])
            if a.get("size"):
                session.preferences.size = norm_size(a["size"]) or session.preferences.size
            req = SearchRequest(**{k: a.get(k) for k in ("brand", "model", "color", "category", "size", "max_price", "use_case", "sort", "limit")})
            res = await search_products(self.db, req, inventory=self.inventory)
            exact = [p for p in res.products if not p.is_alternative]
            if not exact and "max_price" in res.relaxed_constraints and a.get("sort") == "price_asc":
                session.preferences.max_price = None  # derived "cheaper" cap was unsatisfiable; do not carry it forward
            return {"query": res.query, "route": res.route, "products": [p.model_dump(mode="json") for p in res.products],
                    "relaxed_constraints": res.relaxed_constraints, "result_count": res.result_count,
                    "inventory_status": res.inventory_status}
        if call.name == "get_store_availability":
            a = args.model_dump()
            size = norm_size(a.get("size")) or session.preferences.size
            if size:
                session.preferences.size = size
            variant_id = await self._resolve_variant(a.get("variant_id"), a.get("model_id"), size, session)
            loc = location_store.resolve(a.get("location_token") or session.location_token)
            if variant_id is None:
                sizes = await self._sizes_for_model(a.get("model_id"), session)
                return {"variant_id": None, "model_id": a.get("model_id"), "size": size, "stores": [], "available_sizes": sizes,
                        "location_known": bool(loc), "inventory_status": "ok", "stock_checked_at": None,
                        "note": "no variant matches that model/size"}
            try:
                stores, checked = await self.inventory.store_availability(variant_id, location=(loc.lat, loc.lon) if loc else None)
            except InventoryUnavailable:
                return {"variant_id": variant_id, "size": size, "stores": [], "inventory_status": "unavailable", "location_known": bool(loc)}
            session.selected_variant_id = variant_id
            sizes = await self._sizes_for_variant(variant_id) if not stores else []
            return {"variant_id": variant_id, "model_id": a.get("model_id"), "size": size,
                    "stores": [StoreAvailability(**{**s, "size": size}).model_dump(mode="json") for s in stores],
                    "stock_checked_at": checked.isoformat(), "location_known": bool(loc), "inventory_status": "ok",
                    "available_sizes": sizes}
        return {"error": "UNKNOWN_TOOL"}

    async def _resolve_variant(self, variant_id: str | None, model_id: str | None, size: str | None, session: Session) -> str | None:
        from sqlalchemy import select

        from ..db import ProductVariant
        backend = get_search_backend()
        if variant_id:
            v = (await self.db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))).scalar_one_or_none()
            if v is None:
                return None
            if size and v.size != size:
                sib = (await self.db.execute(select(ProductVariant).where(ProductVariant.image_group_id == v.image_group_id,
                                                                            ProductVariant.size == size))).scalar_one_or_none()
                return sib.id if sib else None
            return v.id
        if model_id:
            docs = await backend.by_model(model_id)
            if session.preferences.color:
                docs = [d for d in docs if d.primary_color == session.preferences.color] or docs
            if not docs:
                return None
            if size:
                sib = (await self.db.execute(select(ProductVariant).where(ProductVariant.image_group_id == docs[0].doc_id,
                                                                            ProductVariant.size == size))).scalar_one_or_none()
                return sib.id if sib else None
            return docs[0].variant_ids[0]
        return None

    async def _sizes_for_variant(self, variant_id: str) -> list[str]:
        from sqlalchemy import select

        from ..db import ProductVariant
        v = (await self.db.execute(select(ProductVariant).where(ProductVariant.id == variant_id))).scalar_one_or_none()
        if not v:
            return []
        sibs = (await self.db.execute(select(ProductVariant.id).where(ProductVariant.image_group_id == v.image_group_id))).scalars().all()
        try:
            stock = await self.inventory.batch_stock(list(sibs))
        except InventoryUnavailable:
            return []
        return sorted({s.size for s in stock.values()}, key=float)

    async def _sizes_for_model(self, model_id: str | None, session: Session) -> list[str]:
        if not model_id:
            return []
        docs = await get_search_backend().by_model(model_id)
        if not docs:
            return []
        return await self._sizes_for_variant(docs[0].variant_ids[0])

    @staticmethod
    def _ground(text: str, products: list[ProductCard], stores: list[StoreAvailability] | None) -> str:
        """Light grounding guard: strip firm stock claims when nothing was verified in stock."""
        lowered = text.lower()
        if not products and stores is None and ("in stock" in lowered and "not" not in lowered and "no " not in lowered):
            return text + " (Note: I could not verify stock for this.)"
        return text[:600]
