"""Deterministic query router: exact model → indexed lookup; attributes → filters; descriptive → text.

Only candidate IDs from search are verified in ONE batched inventory query. Returns 3–5 in-stock cards,
or clearly labelled alternatives when hard filters yield nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ..inventory.service import InventoryService, InventoryUnavailable, StockSummary
from ..schemas import ProductCard
from .index import Hit, SearchQuery, get_search_backend
from .normalize import norm_brand, norm_category, norm_color, norm_model_id, norm_size

CANDIDATE_BATCH = 20
MAX_BATCHES = 3


@dataclass
class SearchRequest:
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    category: str | None = None
    size: str | None = None
    max_price: float | None = None
    use_case: str | None = None
    sort: str = "relevance"
    limit: int = 5
    exclude_variant_ids: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    products: list[ProductCard]
    relaxed_constraints: list[str]
    route: str
    result_count: int
    inventory_status: str = "ok"
    query: dict = field(default_factory=dict)


def _card(hit: Hit, summary: StockSummary | None, *, alternative: bool = False, relaxed: list[str] | None = None,
          inventory_unknown: bool = False) -> ProductCard:
    d = hit.doc
    confidence = "verified" if d.color_verified else ("unverified" if d.primary_color else "unknown")
    return ProductCard(
        product_id=d.product_id, variant_id=(summary.best_variant_id if summary else d.variant_ids[0]) or d.variant_ids[0],
        model_id=d.model_id, name=d.name, brand=d.brand, primary_color=d.primary_color, color_confidence=confidence,
        category=d.category, price=d.price_min, currency=d.currency, image_url=d.image_url,
        available_sizes=summary.available_sizes if summary else [], in_stock=bool(summary),
        stock_status="unknown" if inventory_unknown else ("in_stock" if summary else "out_of_stock"),
        stock_checked_at=summary.checked_at if summary else None, store_count=summary.store_count if summary else 0,
        image_group_id=d.doc_id, is_alternative=alternative, relaxed=relaxed or [])


def choose_route(req: SearchRequest) -> str:
    if norm_model_id(req.model) or norm_model_id(req.use_case or ""):
        return "exact_model"
    if req.model:
        return "model_text"
    if req.brand or req.color or req.category:
        return "attribute"
    return "text"


def to_query(req: SearchRequest, *, relax: set[str] = frozenset()) -> SearchQuery:
    model_id = norm_model_id(req.model) or norm_model_id(req.use_case or "")
    return SearchQuery(
        brand=None if "brand" in relax else norm_brand(req.brand),
        model_id=model_id,
        model_text=None if (model_id or "model" in relax) else req.model,
        color=None if "color" in relax else norm_color(req.color),
        category=None if "category" in relax else norm_category(req.category),
        size=None if "size" in relax else norm_size(req.size),
        max_price=None if "max_price" in relax else req.max_price,
        text=req.use_case if "use_case" not in relax else None,
        limit=CANDIDATE_BATCH * MAX_BATCHES,
    )


async def _verified(hits: list[Hit], inv: InventoryService, size: str | None, limit: int,
                    exclude: set[str]) -> tuple[list[tuple[Hit, StockSummary]], bool]:
    """Batch-check candidates in bounded batches until `limit` in-stock results are found."""
    results: list[tuple[Hit, StockSummary]] = []
    for b in range(MAX_BATCHES):
        batch = hits[b * CANDIDATE_BATCH:(b + 1) * CANDIDATE_BATCH]
        if not batch:
            break
        groups = {h.doc.doc_id: [v for v in h.doc.variant_ids if v not in exclude] for h in batch}
        summaries = await inv.summarize_groups(groups, size=size)
        for h in batch:
            if h.doc.doc_id in summaries:
                results.append((h, summaries[h.doc.doc_id]))
        if len(results) >= limit:
            break
    return results[:limit], len(results) >= limit


async def search_products(db: AsyncSession, req: SearchRequest, *, inventory: InventoryService | None = None) -> SearchResult:
    inv = inventory or InventoryService(db)
    backend = get_search_backend()
    route = choose_route(req)
    limit = max(3, min(5, req.limit or 5))
    q = to_query(req)
    size = q.size
    exclude = set(req.exclude_variant_ids)

    if route == "exact_model" and q.model_id:
        hits = [Hit(doc=d, score=10.0, matched={"model": "exact"}) for d in await backend.by_model(q.model_id)]
        if q.color:
            hits = [h for h in hits if h.doc.primary_color == q.color] or hits
    else:
        hits = await backend.search(q)
    if req.sort == "price_asc":
        hits.sort(key=lambda h: h.doc.price_min)
    elif req.sort == "price_desc":
        hits.sort(key=lambda h: -h.doc.price_min)

    query_dict = {k: v for k, v in {"brand": q.brand, "model_id": q.model_id, "color": q.color, "category": q.category,
                                    "size": size, "max_price": q.max_price, "use_case": q.text}.items() if v is not None}
    try:
        verified, _ = await _verified(hits, inv, size, limit, exclude)
    except InventoryUnavailable:
        cards = [_card(h, None, inventory_unknown=True) for h in hits[:limit]]
        return SearchResult(products=cards, relaxed_constraints=[], route=route, result_count=len(cards),
                            inventory_status="unavailable", query=query_dict)

    cards = [_card(h, s) for h, s in verified]
    relaxed: list[str] = []
    if len(cards) < 3:
        # Alternatives: relax non-essential constraints in a fixed order; never silently drop brand/model.
        have = {c.image_group_id for c in cards}
        for relax_set in (["size"], ["max_price"], ["size", "max_price"], ["category"], ["size", "max_price", "category"],
                          ["color"], ["size", "max_price", "category", "color"]):
            rs = set(relax_set)
            if q.model_id and "size" not in rs:
                continue  # for exact-model queries only size relaxation makes sense
            active = [r for r in relax_set if query_dict.get("size" if r == "size" else r) is not None]
            if not active:
                continue
            rq = to_query(req, relax=rs)
            alt_hits = [h for h in (await backend.search(rq)) if h.doc.doc_id not in have]
            try:
                alt_verified, _ = await _verified(alt_hits, inv, None if "size" in rs else size, limit - len(cards), exclude)
            except InventoryUnavailable:
                break
            for h, s in alt_verified:
                cards.append(_card(h, s, alternative=True, relaxed=active))
                have.add(h.doc.doc_id)
            if alt_verified:
                relaxed = sorted(set(relaxed) | set(active))
            if len(cards) >= 3:
                break
    return SearchResult(products=cards[:limit], relaxed_constraints=relaxed, route=route, result_count=len(cards[:limit]),
                        query=query_dict)
