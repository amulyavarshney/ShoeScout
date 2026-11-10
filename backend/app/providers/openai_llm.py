"""OpenAI Responses API adapter with function calling (no SDK; explicit tool-loop envelope)."""
from __future__ import annotations

import json

import httpx

from .base import AgentRequest, AgentResponse, ProviderError, ToolCall

OPENAI_BASE = "https://api.openai.com/v1"


class OpenAILLMProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, *, timeout_s: int = 20) -> None:
        self._key = api_key
        self.model = model
        self.timeout = timeout_s

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def _build_input(self, request: AgentRequest) -> list[dict]:
        if request.previous_response_id and request.tool_results:
            # Chained pattern: only function_call_output items are needed.
            return [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)}
                    for call, result in request.tool_results]
        items: list[dict] = []
        for m in request.messages:
            items.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["text"]})
        for call, result in request.tool_results:
            items.append({"type": "function_call", "call_id": call.call_id, "name": call.name, "arguments": json.dumps(call.arguments)})
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
        return items

    async def respond(self, request: AgentRequest) -> AgentResponse:
        body = {"model": request.model or self.model, "instructions": request.system_prompt,
                "input": self._build_input(request), "tools": request.tools, "tool_choice": "auto",
                "parallel_tool_calls": False, "store": True, "max_output_tokens": 400}
        if request.previous_response_id and request.tool_results:
            body["previous_response_id"] = request.previous_response_id
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{OPENAI_BASE}/responses", headers=self._headers(), json=body)
        except httpx.TimeoutException as e:
            raise ProviderError("LLM_TIMEOUT", "LLM request timed out", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError("LLM_NETWORK", "LLM network error", retryable=True) from e
        if r.status_code == 401:
            raise ProviderError("LLM_AUTH", "OpenAI rejected the API key")
        if r.status_code == 429:
            raise ProviderError("LLM_RATE_LIMITED", "OpenAI rate limit reached", retryable=True)
        if r.status_code >= 400:
            msg = ""
            try:
                msg = r.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise ProviderError("LLM_ERROR", f"OpenAI error {r.status_code}: {msg[:200]}")
        data = r.json()
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for item in data.get("output", []):
            if item.get("type") == "function_call":
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"__invalid__": item.get("arguments")}
                calls.append(ToolCall(call_id=item["call_id"], name=item["name"], arguments=args, raw_item=item))
            elif item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        text_parts.append(c.get("text", ""))
        return AgentResponse(text="".join(text_parts).strip() or None, tool_calls=calls, response_id=data.get("id"),
                             raw_output=data.get("output", []))

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{OPENAI_BASE}/models/{self.model}", headers=self._headers())
        if r.status_code == 401:
            return {"ok": False, "error_type": "auth", "message": "API key rejected"}
        if r.status_code == 404:
            return {"ok": False, "error_type": "model_not_found", "message": f"Model '{self.model}' not available to this key"}
        if r.status_code >= 400:
            return {"ok": False, "error_type": "http", "message": f"HTTP {r.status_code}"}
        return {"ok": True, "message": f"Connected; model '{self.model}' available"}
