"""Mock providers for demo mode (no paid keys). Clearly labelled as demo; never claims to be a real provider."""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import AsyncIterator

from ..search.normalize import (BRANDS, CATEGORY_SYNONYMS, COLOR_SYNONYMS, norm_brand, norm_category, norm_color,
                                norm_model_id, norm_size)
from .base import AgentRequest, AgentResponse, AudioChunk, ToolCall, TranscriptEvent

USE_CASE_HINTS = ["standing", "shift", "shifts", "all day", "comfortable", "comfort", "work", "walking", "hiking", "gym",
                  "wedding", "office", "school", "winter", "summer", "marathon", "trail", "skate"]


def parse_utterance(text: str, context: dict) -> dict:
    """Deterministic NLU: extracts filters + intent from a sentence, merged with known preferences."""
    t = " " + text.lower().strip() + " "
    prefs = dict(context.get("preferences") or {})
    out = {"intent": "search", "updates": {}, "sort": "relevance", "cheaper": False, "store": False, "alternatives": False,
           "clarify_size": False, "reset": False}

    if re.search(r"\b(start over|reset|new search|forget)\b", t):
        out["reset"] = True
        prefs = {}

    for b in sorted(BRANDS, key=len, reverse=True):
        if f" {b} " in t or f" {b}s " in t:
            out["updates"]["brand"] = norm_brand(b)
            break
    for c in sorted(COLOR_SYNONYMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", t):
            out["updates"]["color"] = norm_color(c)
            break
    for c in sorted(CATEGORY_SYNONYMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", t):
            cat = norm_category(c)
            if cat:
                out["updates"]["category"] = cat
                break
    m = re.search(r"\bsize\s*(?:uk\s*)?(\d{1,2}(?:\.5)?)\b", t) or re.search(r"\b(?:in|a)\s+(\d{1,2}(?:\.5)?)\b", t) \
        or (re.fullmatch(r"\s*(?:uk\s*)?(\d{1,2}(?:\.5)?)\s*", t) and re.search(r"(\d{1,2}(?:\.5)?)", t))
    if m:
        out["updates"]["size"] = norm_size(m.group(1))
    m = re.search(r"(?:under|below|less than|max|up to|budget of|cheaper than)\s*[£$€]?\s*(\d{2,4})", t) or re.search(r"[£$€]\s*(\d{2,4})", t)
    if m:
        out["updates"]["max_price"] = float(m.group(1))
    model_id = norm_model_id(text)
    if model_id:
        out["updates"]["model"] = model_id
    if any(h in t for h in USE_CASE_HINTS) and "category" not in out["updates"]:
        out["updates"]["use_case"] = text.strip()[:120]

    # Topic shifts: a model ID names a specific shoe, and a fresh use-case sentence with no other filters starts a
    # new need. In both cases earlier attribute filters are dropped (size is kept: it belongs to the shopper).
    explicit_filters = {k for k in ("brand", "color", "category", "max_price") if k in out["updates"]}
    if model_id:
        out["reset_keys"] = ["brand", "color", "category", "use_case", "max_price"]
    elif "use_case" in out["updates"] and not explicit_filters:
        out["reset_keys"] = ["brand", "color", "category", "model", "max_price"]
    elif explicit_filters or out["alternatives"]:
        out["reset_keys"] = ["model"]  # new attributes replace a previously named model
    else:
        out["reset_keys"] = []

    if re.search(r"\bcheaper|less expensive|lower price|budget\b", t):
        out["cheaper"] = True
        out["sort"] = "price_asc"
    if re.search(r"\b(more expensive|premium|pricier)\b", t):
        out["sort"] = "price_desc"
    if re.search(r"\b(store|stores|shop|nearest|near me|nearby|which branch|in stock near|where can i)\b", t):
        out["store"] = True
    if re.search(r"\b(similar|alternative|alternatives|something like|instead)\b", t):
        out["alternatives"] = True
    if re.search(r"\b(available|in stock|do you have|have you got)\b", t) and (model_id or context.get("selected_variant_id")):
        out["store"] = out["store"] or bool(context.get("selected_variant_id")) and not model_id
    out["known"] = prefs
    return out


class MockLLMProvider:
    """Rule-based planner that emits the same tool calls a real LLM would, then a grounded summary."""
    name = "mock"

    async def respond(self, request: AgentRequest) -> AgentResponse:
        await asyncio.sleep(0.05)
        ctx = request.context
        user_text = next((m["text"] for m in reversed(request.messages) if m["role"] == "user"), "")
        if request.tool_results:
            return AgentResponse(text=self._summarize(request), tool_calls=[], response_id=None)

        parsed = parse_utterance(user_text, ctx)
        known = {k: v for k, v in parsed["known"].items() if v is not None and k not in parsed["reset_keys"]}
        merged = {**known, **parsed["updates"]}
        if parsed["reset_keys"]:
            ctx["reset_keys"] = parsed["reset_keys"]
        selected = ctx.get("selected_variant_id")
        last_results = ctx.get("last_results") or []

        if parsed["store"]:
            variant_id = selected or (last_results[0]["variant_id"] if last_results else None)
            model_id = merged.get("model")
            if not variant_id and not model_id:
                return AgentResponse(text="Which shoe would you like me to check in store? Pick a product first, or tell me the model.", tool_calls=[])
            if not merged.get("size"):
                return AgentResponse(text="What shoe size should I check store stock for?", tool_calls=[])
            if not ctx.get("location_token") and re.search(r"nearest|near me|nearby|closest", user_text.lower()):
                return AgentResponse(text="To find the nearest store I need your location. Share it with the location button or tell me your postcode or city.", tool_calls=[])
            args = {"variant_id": variant_id if not model_id else None, "model_id": model_id, "size": merged.get("size"),
                    "location_token": ctx.get("location_token")}
            return AgentResponse(text=None, tool_calls=[ToolCall(call_id=f"mock_{uuid.uuid4().hex[:8]}", name="get_store_availability", arguments=args)])

        if parsed["cheaper"] and last_results and "max_price" not in parsed["updates"]:
            priciest = max(r["price"] for r in last_results)
            merged["max_price"] = max(1.0, priciest - 0.01)  # strictly cheaper than the most expensive shown
        if not any(merged.get(k) for k in ("brand", "color", "category", "model", "use_case", "max_price")):
            if parsed["updates"].get("size") and last_results:
                pass  # size-only follow-up: re-run previous search with size
            else:
                return AgentResponse(text="Tell me what you're looking for, for example a brand, colour, type of shoe, or what you need them for.", tool_calls=[])
        args = {"brand": merged.get("brand"), "model": merged.get("model"), "color": merged.get("color"),
                "category": merged.get("category"), "size": merged.get("size"), "max_price": merged.get("max_price"),
                "use_case": merged.get("use_case"), "sort": parsed["sort"], "limit": 5}
        return AgentResponse(text=None, tool_calls=[ToolCall(call_id=f"mock_{uuid.uuid4().hex[:8]}", name="search_products", arguments=args)])

    @staticmethod
    def _summarize(request: AgentRequest) -> str:
        call, result = request.tool_results[-1]
        cur = request.context.get("currency", "GBP")
        sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(cur, cur + " ")
        if call.name == "search_products":
            if result.get("error"):
                return "I couldn't complete that search right now. Please try again or type your request."
            products = result.get("products", [])
            if result.get("inventory_status") == "unavailable":
                return "Availability is temporarily unavailable, so I can't confirm stock. Here are matching products; please check back shortly."
            if not products:
                q = result.get("query", {})
                parts = [f"{k.replace('_', ' ')} {v}" for k, v in q.items()]
                return f"I couldn't find in-stock shoes matching {', '.join(parts) if parts else 'that'}. Want me to relax one of those, like the colour or budget?"
            exact = [p for p in products if not p.get("is_alternative")]
            alts = [p for p in products if p.get("is_alternative")]
            prices = [p["price"] for p in (exact or alts)]  # spoken range covers the primary set only
            desc = []
            q = result.get("query", {})
            shown = exact or alts
            colors = {p.get("primary_color") for p in shown}
            brands = {p.get("brand") for p in shown}
            if len(colors) == 1 and None not in colors:
                desc.append(next(iter(colors)))
            if len(brands) == 1:
                desc.append(next(iter(brands)))
            label = " ".join(desc) + " " if desc else ""
            if exact:
                msg = f"I found {len(exact)} {label}option{'s' if len(exact) != 1 else ''} in stock, from {sym}{min(prices):.0f} to {sym}{max(prices):.0f}."
            else:
                msg = f"I couldn't find an exact match in stock, so here are {len(alts)} close alternatives."
            if alts and exact:
                relaxed = result.get("relaxed_constraints", [])
                msg += f" I added {len(alts)} alternative{'s' if len(alts) != 1 else ''} by relaxing {', '.join(r.replace('_', ' ') for r in relaxed)}."
            elif alts and not exact:
                relaxed = result.get("relaxed_constraints", [])
                if relaxed == ["size"] and q.get("size"):
                    sizes = sorted({s for p in alts for s in p.get("available_sizes", [])}, key=float)
                    msg = f"Size {q['size']} isn't in stock for that. Here {'is' if len(alts) == 1 else 'are'} {len(alts)} option{'s' if len(alts) != 1 else ''} in stock in size{'s' if len(sizes) != 1 else ''} {', '.join(sizes)}."
                elif relaxed:
                    msg += f" They relax your {', '.join(r.replace('_', ' ') for r in relaxed)}."
            if not q.get("size") and "size" not in (result.get("relaxed_constraints") or []):
                msg += " What size do you need?"
            return msg
        if call.name == "get_store_availability":
            if result.get("error") or result.get("inventory_status") == "unavailable":
                return "Store availability is temporarily unavailable. Please try again in a moment."
            stores = result.get("stores", [])
            size = result.get("size")
            if not stores:
                sizes = result.get("available_sizes", [])
                extra = f" It is in stock in size{'s' if len(sizes) != 1 else ''} {', '.join(sizes)}." if sizes else ""
                return f"No store currently has that shoe in size {size}.{extra} Would you like alternatives?"
            first = stores[0]
            if result.get("location_known") and first.get("distance_km") is not None:
                return f"The nearest store with size {size} is {first['name']}, about {first['distance_km']} km away. {len(stores)} store{'s' if len(stores) != 1 else ''} in total have it."
            names = ", ".join(s["name"] for s in stores[:3])
            return f"Size {size} is in stock at {len(stores)} store{'s' if len(stores) != 1 else ''}: {names}. Share your location if you want the nearest one."
        return "Done."


class MockSTTProvider:
    """Mock STT cannot transcribe audio; the browser falls back to typed input / Web Speech in demo mode."""
    name = "mock"

    def __init__(self) -> None:
        self._q: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()

    async def connect(self) -> None:
        return None

    async def send_audio(self, pcm16: bytes, *, commit: bool = False) -> None:
        if commit:
            await self._q.put(TranscriptEvent(kind="error", error="STT_UNAVAILABLE"))

    async def commit(self) -> None:
        await self._q.put(TranscriptEvent(kind="error", error="STT_UNAVAILABLE"))

    async def events(self) -> AsyncIterator[TranscriptEvent]:
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        await self._q.put(None)


class MockTTSProvider:
    """Produces no audio; the client uses browser speech synthesis in demo mode."""
    name = "mock"
    codec = "none"
    sample_rate = 0

    async def stream_audio(self, text: str, voice_id: str) -> AsyncIterator[AudioChunk]:
        if False:
            yield AudioChunk(b"")
        return


class MockVisionProvider:
    """Deterministic demo vision: derives attributes from the demo fixture; labelled 'fixture', not a real model."""
    name = "mock"
    model_version = "mock-vision-fixture-v1"

    async def extract_attributes(self, images: list[str], description: str) -> dict:
        from ..seed.demo_catalog import fixture_attributes
        await asyncio.sleep(0.01)
        fx = fixture_attributes()
        for url in images:
            if url.startswith("https://example.invalid"):
                raise RuntimeError("IMAGE_FETCH_FAILED: host not allowlisted / unreachable")
            key = url.rsplit("/", 1)[-1].replace(".svg", "").upper()
            for gid, attrs in fx.items():
                if gid.upper() == key:
                    return {"primary_color": attrs["primary_color"] if attrs["review_status"] == "approved" else attrs["evidence"].get("vision_color"),
                            "secondary_colors": attrs["secondary_colors"], "style": attrs["style"], "category": attrs["category"],
                            "tags": attrs["tags"], "closure": "unknown", "material": "unknown"}
        return {"primary_color": "unknown", "secondary_colors": [], "style": "unknown", "category": "unknown", "tags": [],
                "closure": "unknown", "material": "unknown"}
