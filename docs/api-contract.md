# API contract (summary)

Base: `/api/v1`. Errors: `{"error":{"code","message","request_id"}}`. OpenAPI: `/api/openapi.json`, docs `/api/docs`.

## Shopper
| Method | Route | Notes |
|---|---|---|
| POST | `/sessions` | → `{session_id, expires_at, mode, capabilities}` |
| POST | `/sessions/{id}/messages` | `{text, turn_id}` → `{message, products[], stores?, preferences, state, relaxed_constraints, is_demo}`; 409 on duplicate turn |
| GET | `/sessions/{id}` | preferences, selected variant, recent messages |
| POST | `/sessions/{id}/select` | `{variant_id}` |
| POST | `/sessions/{id}/location/consent` | `{latitude,longitude}` or `{postcode}`/`{city}` → `{location_token, expires_at, label}` |
| DELETE | `/sessions/{id}` | clears ephemeral memory |
| GET | `/products/search` | `brand,color,model,category,size,max_price,q,sort,limit` |
| GET | `/products/{id}` | detail with colourways, per-size stock status |
| GET | `/variants/{id}/availability` | `size?, location_token?` → stores (distance only if token valid) |
| GET | `/config/public` | mode + capabilities, never secrets |
| WS | `/ws/voice?session_id=` | see below |

## Admin (cookie + `x-csrf-token` on mutations)
`POST /admin/login`, `POST /admin/logout`, `GET /admin/auth/status`, `GET /admin/providers`, `PUT|DELETE /admin/providers/{p}/key`, `POST /admin/providers/{p}/test`, `GET /admin/providers/elevenlabs/voices`, `GET|PATCH /admin/settings`, `POST /admin/settings/reset-defaults`, `POST /admin/catalog/seed-demo`, `POST /admin/catalog/import` (JSON/CSV multipart), `POST /admin/enrichment/run`, `GET /admin/enrichment/jobs`, `POST /admin/enrichment/jobs/{id}/retry`, `GET|POST /admin/enrichment/review[/{group}]`, `GET /admin/metrics/summary`.

## WebSocket events
Client → server (JSON): `session.start{audio_format,sample_rate,auto_endpoint}`, `audio.start{turn_id}`, `audio.end{turn_id}`, `text.turn{turn_id,text,speak}`, `turn.cancel{turn_id}`, `session.stop`, `ping`. Binary frames = PCM16 audio.

Server → client (JSON): `session.ready{mode,server_stt,server_tts,silence_ms}`, `stt.partial`, `stt.final`, `vad.speech_start`, `vad.no_speech`, `audio.level`, `agent.state{state: listening|finalizing|thinking|searching|speaking}`, `tool.called`, `search.results{products,relaxed_constraints,inventory_status}`, `store.results{stores,variant_id,size,location_known}`, `agent.message{text,preferences,selected_variant_id,is_demo}`, `tts.start{codec,sample_rate}` … binary audio … `tts.end{cancelled}`, `tts.unavailable`, `turn.complete`, `turn.cancelled`, `error{code,message}`. Every turn-scoped event carries `turn_id`; clients ignore stale turns.
