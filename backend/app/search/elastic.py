"""Elasticsearch adapter (optional; selected when ELASTICSEARCH_URL is set).

Uses a versioned index + alias swap on rebuild. Query semantics mirror the in-memory backend.
"""
from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from .index import Hit, SearchDoc, SearchQuery, build_docs

ALIAS = "shoescout-products"
MAPPING = {
    "mappings": {"properties": {
        "product_id": {"type": "keyword"}, "model_id": {"type": "keyword"}, "brand": {"type": "keyword"},
        "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}}, "primary_color": {"type": "keyword"},
        "secondary_colors": {"type": "keyword"}, "category": {"type": "keyword"}, "description": {"type": "text"},
        "tags": {"type": "keyword"}, "image_group_id": {"type": "keyword"}, "variant_ids": {"type": "keyword"},
        "sizes": {"type": "keyword"}, "price_min": {"type": "scaled_float", "scaling_factor": 100},
        "color_verified": {"type": "boolean"}, "image_url": {"type": "keyword"}, "currency": {"type": "keyword"},
    }}
}


class ElasticsearchBackend:
    def __init__(self, url: str) -> None:
        from elasticsearch import AsyncElasticsearch
        self.es = AsyncElasticsearch(url)
        self._cache: dict[str, SearchDoc] = {}

    @staticmethod
    def _to_source(d: SearchDoc) -> dict:
        return {"product_id": d.product_id, "model_id": d.model_id, "brand": d.brand, "name": d.name,
                "description": d.description, "category": d.category, "primary_color": d.primary_color,
                "secondary_colors": d.secondary_colors, "tags": d.tags, "image_group_id": d.doc_id,
                "variant_ids": d.variant_ids, "sizes": d.sizes, "price_min": d.price_min,
                "color_verified": d.color_verified, "image_url": d.image_url, "currency": d.currency}

    @staticmethod
    def _from_source(s: dict) -> SearchDoc:
        return SearchDoc(doc_id=s["image_group_id"], product_id=s["product_id"], model_id=s["model_id"], brand=s["brand"],
                         name=s["name"], description=s.get("description", ""), category=s.get("category"),
                         primary_color=s.get("primary_color"), secondary_colors=s.get("secondary_colors", []),
                         color_verified=bool(s.get("color_verified")), tags=s.get("tags", []), image_url=s.get("image_url"),
                         variant_ids=s["variant_ids"], sizes=s.get("sizes", []), price_min=s["price_min"], currency=s.get("currency", "GBP"))

    async def rebuild(self, db: AsyncSession) -> int:
        docs = await build_docs(db)
        self._cache = {d.doc_id: d for d in docs}
        name = f"{ALIAS}-{int(time.time())}"
        await self.es.indices.create(index=name, **MAPPING)
        for d in docs:
            await self.es.index(index=name, id=d.doc_id, document=self._to_source(d))
        await self.es.indices.refresh(index=name)
        actions = [{"add": {"index": name, "alias": ALIAS}}]
        old_indices: list[str] = []
        try:
            old_indices = list(await self.es.indices.get_alias(name=ALIAS))
            for idx in old_indices:
                actions.insert(0, {"remove": {"index": idx, "alias": ALIAS}})
        except Exception:
            pass
        await self.es.indices.update_aliases(actions=actions)
        for idx in old_indices:  # atomic swap done; drop superseded versions
            try:
                await self.es.indices.delete(index=idx)
            except Exception:
                pass
        return len(docs)

    async def get(self, doc_id: str) -> SearchDoc | None:
        if doc_id in self._cache:
            return self._cache[doc_id]
        try:
            r = await self.es.get(index=ALIAS, id=doc_id)
            return self._from_source(r["_source"])
        except Exception:
            return None

    async def by_model(self, model_id: str) -> list[SearchDoc]:
        r = await self.es.search(index=ALIAS, query={"term": {"model_id": model_id.upper()}}, size=20)
        return [self._from_source(h["_source"]) for h in r["hits"]["hits"]]

    async def search(self, q: SearchQuery) -> list[Hit]:
        filters: list[dict] = []
        should: list[dict] = []
        if q.model_id:
            filters.append({"term": {"model_id": q.model_id.upper()}})
        if q.brand:
            filters.append({"term": {"brand": q.brand}})
        if q.category:
            filters.append({"term": {"category": q.category}})
        if q.size:
            filters.append({"term": {"sizes": q.size}})
        if q.max_price is not None:
            filters.append({"range": {"price_min": {"lte": q.max_price}}})
        if q.color:
            filters.append({"bool": {"should": [{"term": {"primary_color": q.color}}, {"term": {"secondary_colors": q.color}}],
                                     "minimum_should_match": 1}})
            should.append({"term": {"primary_color": {"value": q.color, "boost": 2.0}}})
        if q.model_text:
            filters.append({"match": {"name": {"query": q.model_text, "operator": "and"}}})
        if q.text:
            should.append({"multi_match": {"query": q.text, "fields": ["name^2", "description", "tags^2"]}})
        body = {"bool": {"filter": filters, "should": should}}
        if q.text and not (q.brand or q.color or q.category or q.model_id):
            body["bool"]["minimum_should_match"] = 1
        r = await self.es.search(index=ALIAS, query=body, size=q.limit, sort=["_score", {"price_min": "asc"}])
        return [Hit(doc=self._from_source(h["_source"]), score=h.get("_score") or 1.0, matched={}) for h in r["hits"]["hits"]]
