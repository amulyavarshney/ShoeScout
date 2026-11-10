# ShoeScout architecture

## Principles
1. **One controller, specialised retrieval paths.** The LLM sees two small tools. The backend routes deterministically: exact `MODEL-xxx` → indexed lookup; brand/colour/category → attribute filters; descriptive need → text search; store questions → direct inventory read (no product search).
2. **Search never claims stock.** Candidates (top 20) come from the index; a single batched inventory query verifies `(variant, store)` quantities before anything is shown. Inventory failure → `stock_status: unknown`.
3. **Offline enrichment, online lookups.** Vision runs in a worker, keyed by `(image_group_id, image_hash, model_version)`. Customer turns only hit indexed attributes.
4. **Demo mode is honest.** Mock providers are labelled; the fixture is labelled `fixture`; nothing pretends a real provider ran.
5. **Secrets stay server-side.** Encrypted at rest, masked in APIs, versioned for safe invalidation.

## Turn lifecycle (voice)
1. `session.start` → gateway loads effective config (version N), connects ElevenLabs STT if live.
2. `audio.start` + PCM16 frames → forwarded to STT; EnergyVAD frames → TurnDetector.
3. `endpoint` (silence ≥ `silence_ms`, speech ≥ 200 ms) → `commit` to STT → wait for committed transcript (fallback: last partial after 6 s).
4. One `turn_id` → `AgentController.handle_turn` (idempotent; duplicate/stale turns rejected) → ≤3 LLM rounds → tools → `search.results` / `store.results` events stream to the browser as soon as tools return.
5. `agent.message` → TTS stream (binary frames) → `turn.complete`. `turn.cancel` or a new `audio.start` cancels playback (barge-in).

Typed turns (`POST /sessions/{id}/messages` or `text.turn` over the socket) run the **same** controller.

## Memory
`Session` holds structured `preferences`, `selected_variant_id`, compact `last_results`, last 10 messages, `location_token`, processed turn IDs. Preference merge is validated: explicit values override, `null` leaves values intact. Topic shifts (a new model ID, or a fresh use-case sentence with no other filters) reset earlier attribute filters; a derived "cheaper" price cap that turns out unsatisfiable is not carried forward.

## Data
- **DB (SQLite dev / Postgres)**: products, product_variants, product_images, enriched_attributes, stores, inventory `(variant_id, store_id)`, enrichment_jobs, provider_credentials (ciphertext), provider_settings, analytics_events, audit_log.
- **Search index**: one doc per colourway/image group (`brand`, `model_id`, `primary_color`, `secondary_colors`, `category`, `tags`, `sizes`, `variant_ids`, `price_min`). In-memory by default; Elasticsearch adapter with versioned index + alias swap when `ELASTICSEARCH_URL` is set.
- **Sessions**: in-memory TTL store by default; Redis adapter when `REDIS_URL` is set.

## Latency instrumentation
Per-turn timings (`llm_round_n`, `tool_*`, `total`) and `speech_end_to_first_audio` are recorded; `/admin/metrics/summary` exposes p50/p95 per stage plus anonymised counters.

## What is P1 / not done
Semantic/vector retrieval, Silero/WebRTC VAD (interface is in place), streaming LLM→TTS chunking, map view, favourites, load tests, SSO. Barge-in cancels stale playback and supersedes turns, but a partially streamed LLM answer is not retried.
