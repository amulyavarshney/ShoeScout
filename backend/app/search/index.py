"""In-process search index (default backend) with the same interface as the Elasticsearch adapter.

One searchable document per colorway/image group. Stock is never stored here; candidates are
verified against inventory in a batched query by the retrieval router.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import EnrichedAttributes, Product, ProductImage, ProductVariant
from .normalize import tokenize


@dataclass
class SearchDoc:
    doc_id: str               # image_group_id
    product_id: str
    model_id: str
    brand: str
    name: str
    description: str
    category: str | None
    primary_color: str | None
    secondary_colors: list[str]
    color_verified: bool      # approved attributes (supplier/vision/reviewed) vs needs_review/unknown
    tags: list[str]
    image_url: str | None
    variant_ids: list[str]
    sizes: list[str]
    price_min: float
    currency: str
    text_tokens: set[str] = field(default_factory=set)


@dataclass
class SearchQuery:
    brand: str | None = None
    model_id: str | None = None
    model_text: str | None = None
    color: str | None = None
    category: str | None = None
    size: str | None = None
    max_price: float | None = None
    text: str | None = None
    limit: int = 20


@dataclass
class Hit:
    doc: SearchDoc
    score: float
    matched: dict


class SearchBackend(Protocol):
    async def rebuild(self, db: AsyncSession) -> int: ...
    async def search(self, q: SearchQuery) -> list[Hit]: ...
    async def get(self, doc_id: str) -> SearchDoc | None: ...
    async def by_model(self, model_id: str) -> list[SearchDoc]: ...


async def build_docs(db: AsyncSession) -> list[SearchDoc]:
    products = {p.id: p for p in (await db.execute(select(Product))).scalars()}
    variants = (await db.execute(select(ProductVariant).where(ProductVariant.active == True))).scalars().all()  # noqa: E712
    attrs = {a.image_group_id: a for a in (await db.execute(select(EnrichedAttributes))).scalars()}
    images: dict[str, str] = {}
    for img in (await db.execute(select(ProductImage).order_by(ProductImage.sort_order))).scalars():
        images.setdefault(img.image_group_id, img.url)

    groups: dict[str, list[ProductVariant]] = {}
    for v in variants:
        groups.setdefault(v.image_group_id, []).append(v)

    docs: list[SearchDoc] = []
    for gid, vs in groups.items():
        p = products[vs[0].product_id]
        a = attrs.get(gid)
        tags = list(a.tags) if a else []
        tokens = set(tokenize(" ".join([p.name, p.brand, p.description, p.category or "", a.style if a and a.style else "", *tags])))
        docs.append(SearchDoc(
            doc_id=gid, product_id=p.id, model_id=p.model_id, brand=p.brand, name=p.name, description=p.description,
            category=(a.category if a and a.category else p.category),
            primary_color=a.primary_color if a else None,
            secondary_colors=list(a.secondary_colors) if a else [],
            color_verified=bool(a and a.review_status == "approved" and a.primary_color),
            tags=tags, image_url=images.get(gid), variant_ids=[v.id for v in vs],
            sizes=sorted({v.size for v in vs}, key=lambda s: float(s)), price_min=min(v.price for v in vs),
            currency=vs[0].currency, text_tokens=tokens))
    return docs


class InMemorySearchBackend:
    def __init__(self) -> None:
        self._docs: dict[str, SearchDoc] = {}

    async def rebuild(self, db: AsyncSession) -> int:
        docs = await build_docs(db)
        self._docs = {d.doc_id: d for d in docs}
        return len(docs)

    async def get(self, doc_id: str) -> SearchDoc | None:
        return self._docs.get(doc_id)

    async def by_model(self, model_id: str) -> list[SearchDoc]:
        return [d for d in self._docs.values() if d.model_id.upper() == model_id.upper()]

    async def search(self, q: SearchQuery) -> list[Hit]:
        hits: list[Hit] = []
        text_tokens = set(tokenize(q.text)) if q.text else set()
        model_text_tokens = set(tokenize(q.model_text)) if q.model_text else set()
        for d in self._docs.values():
            matched: dict = {}
            # Hard filters
            if q.model_id and d.model_id.upper() != q.model_id.upper():
                continue
            if q.brand and d.brand.lower() != q.brand.lower():
                continue
            if q.color:
                if d.primary_color == q.color:
                    matched["color"] = "primary"
                elif q.color in d.secondary_colors:
                    matched["color"] = "secondary"
                else:
                    continue
            if q.category and (d.category or "").lower() != q.category.lower():
                continue
            if q.size and q.size not in d.sizes:
                continue
            if q.max_price is not None and d.price_min > q.max_price:
                continue
            if model_text_tokens and not model_text_tokens.issubset(d.text_tokens):
                continue
            # Ranking (deterministic)
            score = 1.0
            if q.brand:
                score += 2.0
            if matched.get("color") == "primary":
                score += 2.0 + (0.5 if d.color_verified else 0.0)
            elif matched.get("color") == "secondary":
                score += 0.5
            if q.category:
                score += 1.0
            if text_tokens:
                overlap = len(text_tokens & d.text_tokens)
                if overlap == 0 and not (q.brand or q.color or q.category or q.model_id):
                    continue
                score += overlap * 0.8
                matched["text_overlap"] = overlap
            if q.max_price is not None:
                score += 0.5 * (1 - d.price_min / max(q.max_price, 1))
            hits.append(Hit(doc=d, score=score, matched=matched))
        hits.sort(key=lambda h: (-h.score, h.doc.price_min, h.doc.name))
        return hits[: q.limit]


_backend: SearchBackend | None = None


def get_search_backend() -> SearchBackend:
    global _backend
    if _backend is None:
        from ..config import get_settings
        url = get_settings().elasticsearch_url
        if url:
            from .elastic import ElasticsearchBackend
            _backend = ElasticsearchBackend(url)
        else:
            _backend = InMemorySearchBackend()
    return _backend


def set_search_backend(backend: SearchBackend) -> None:
    global _backend
    _backend = backend
