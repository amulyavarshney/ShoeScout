"""LLM-visible tool schemas (strict) + server-side validation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

SEARCH_PRODUCTS_SCHEMA = {
    "type": "function",
    "name": "search_products",
    "description": "Find and rank relevant in-stock footwear. Use exact or attribute search when possible; semantic retrieval only when needed.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "brand": {"type": ["string", "null"]},
            "model": {"type": ["string", "null"], "description": "Model name or model ID such as MODEL-101"},
            "color": {"type": ["string", "null"]},
            "category": {"type": ["string", "null"], "description": "running, casual, walking, formal, trail, work, boots, sandals, kids, training"},
            "size": {"type": ["string", "null"]},
            "max_price": {"type": ["number", "null"]},
            "use_case": {"type": ["string", "null"], "description": "Free-text need, e.g. 'standing all day'"},
            "sort": {"type": "string", "enum": ["relevance", "price_asc", "price_desc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["brand", "model", "color", "category", "size", "max_price", "use_case", "sort", "limit"],
        "additionalProperties": False,
    },
}

GET_STORE_AVAILABILITY_SCHEMA = {
    "type": "function",
    "name": "get_store_availability",
    "description": "Get current store stock for a selected product variant or model and optional shoe size.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "variant_id": {"type": ["string", "null"]},
            "model_id": {"type": ["string", "null"]},
            "size": {"type": ["string", "null"]},
            "location_token": {"type": ["string", "null"]},
        },
        "required": ["variant_id", "model_id", "size", "location_token"],
        "additionalProperties": False,
    },
}

TOOLS = [SEARCH_PRODUCTS_SCHEMA, GET_STORE_AVAILABILITY_SCHEMA]
ALLOWED_TOOLS = {t["name"] for t in TOOLS}


class SearchProductsArgs(BaseModel):
    model_config = {"extra": "forbid"}
    brand: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=32)
    size: str | None = Field(default=None, max_length=8)
    max_price: float | None = Field(default=None, ge=0, le=100000)
    use_case: str | None = Field(default=None, max_length=200)
    sort: Literal["relevance", "price_asc", "price_desc"] = "relevance"
    limit: int = Field(default=5, ge=1, le=5)


class GetStoreAvailabilityArgs(BaseModel):
    model_config = {"extra": "forbid"}
    variant_id: str | None = Field(default=None, max_length=64)
    model_id: str | None = Field(default=None, max_length=64)
    size: str | None = Field(default=None, max_length=8)
    location_token: str | None = Field(default=None, max_length=64)


ARG_MODELS = {"search_products": SearchProductsArgs, "get_store_availability": GetStoreAvailabilityArgs}


class ToolValidationError(Exception):
    pass


def validate_tool_call(name: str, raw_args: dict) -> BaseModel:
    if name not in ALLOWED_TOOLS:
        raise ToolValidationError(f"tool '{name}' is not allowed")
    if not isinstance(raw_args, dict):
        raise ToolValidationError("arguments must be an object")
    # Repair: coerce numeric sizes to strings, drop unknown keys rather than execute arbitrary input.
    cleaned = {k: v for k, v in raw_args.items() if k in ARG_MODELS[name].model_fields}
    if "size" in cleaned and isinstance(cleaned["size"], (int, float)):
        cleaned["size"] = str(cleaned["size"]).rstrip("0").rstrip(".") if isinstance(cleaned["size"], float) else str(cleaned["size"])
    if "max_price" in cleaned and isinstance(cleaned["max_price"], str):
        try:
            cleaned["max_price"] = float(cleaned["max_price"].replace("£", "").replace("$", ""))
        except ValueError:
            cleaned["max_price"] = None
    try:
        return ARG_MODELS[name](**cleaned)
    except ValidationError as e:
        raise ToolValidationError(str(e)) from e
