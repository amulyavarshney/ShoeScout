# ShoeScout — voice-first footwear discovery

ShoeScout is a responsive storefront with a **custom voice agent**. A shopper says *"I want red Nike shoes"*, refines conversationally (*"size 9"*, *"show cheaper ones"*, *"actually blue"*), sees 3–5 **in-stock** products as cards, and asks which store carries their size. The whole voice loop (speech-to-text → LLM tool loop → inventory-verified search → text-to-speech) is implemented in this repository on top of the ElevenLabs speech APIs and the OpenAI Responses API. No hosted agent product is used.

- **Demo mode works with zero API keys.** A rule-based planner issues the same tool calls as the LLM, speech runs through the browser's Web Speech API, and every assistant reply is labelled *Demo assistant*.
- **Live mode** switches on when an admin saves OpenAI and ElevenLabs keys in Settings. Keys are AES-GCM encrypted at rest and never reach the browser.
- The UI uses the [ElevenLabs UI](https://ui.elevenlabs.io) component registry (Orb, VoiceButton, Waveform, Conversation, Message, Response, ShimmeringText) on shadcn/ui, with the ElevenLabs neutral theme and Inter.

---

## Contents

1. [Quick start](#quick-start)
2. [Using the app](#using-the-app)
3. [Modes: demo vs live](#modes-demo-vs-live)
4. [Architecture](#architecture)
5. [Configuration](#configuration)
6. [Running with Docker Compose](#running-with-docker-compose)
7. [Tests](#tests)
8. [Security model](#security-model)
9. [Troubleshooting](#troubleshooting)
10. [Known limitations and roadmap](#known-limitations-and-roadmap)
11. [Repository layout](#repository-layout)

---

## Quick start

Prerequisites: **Node 22 + pnpm**, **Python 3.12 + [uv](https://docs.astral.sh/uv/)**. No database or Docker is required for the default setup (SQLite plus an in-process search index).

```bash
git clone <this repo> shoescout && cd shoescout

# 1. Backend
cd backend
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python -r requirements.txt
cat > .env <<'EOF'
APP_ENV=development
MOCK_MODE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-locally
EOF
.venv/bin/uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
pnpm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
pnpm dev
```

Open **http://localhost:3000**. On first start the backend seeds the fictional demo catalogue (34 products, 43 colourways, 200+ size variants, 5 UK stores) and builds the search index.

Admin: **http://localhost:3000/admin/settings**, username `admin`, password = `ADMIN_PASSWORD`.

> **Port already in use?** Run uvicorn on another port (for example `--port 8010`) and set `NEXT_PUBLIC_API_BASE` to match. The frontend derives the WebSocket URL from the same variable.

Or use the Makefile: `make setup`, then `make backend` and `make frontend` in two terminals.

---

## Using the app

**Discovery (home).** Left panel: Orb, *Start talking* button (Space also toggles the mic), live waveform, transcript, and a text box that always works. Right panel: popular categories, featured in-stock products, then the results grid once you ask for something.

Try, in order:

| Say or type | What happens |
|---|---|
| "I want red Nike shoes" | Attribute search → 3–5 red Nike cards verified in stock → asks for your size |
| "size 9" | Keeps Nike + red, re-checks stock for size 9 per store |
| "show cheaper ones" | Keeps preferences, sorts by price, caps below the most expensive shown |
| "actually blue" | Overrides colour, keeps brand and size |
| "Is MODEL-101 available?" | Exact model lookup (no text search), drops earlier attribute filters |
| "Which nearest store has this in size 9?" | Asks for location; after consent, stores sorted by distance |
| "Do you have MODEL-108 in size 9?" | Size 9 is out of stock everywhere: says so, shows the sizes that are in stock as labelled alternatives |
| "comfortable shoes for standing all day" | Use-case text search |

**Product cards** show image, brand, model, verified colour, price, sizes in stock, store count and an *Alternative* badge when a constraint was relaxed. *Find in store* selects the product and asks the agent for store stock. *Details* opens a sheet (mobile: bottom sheet) with colourways, per-size stock, stores, and a *Find nearby stores* prompt that asks for geolocation consent or a postcode.

**Store lists** are alphabetical until a location is shared. Nothing is ever labelled "nearest" without consent.

**Admin → Settings** has four tabs: Providers (keys, model IDs, test connection), Models & voice (voice ID picker, TTS format, silence endpoint, language, mock mode), Catalogue & enrichment (seed, JSON/CSV import, enrichment jobs, review queue), Observability (catalogue counts, per-stage p50/p95 latency, anonymised event counters).

---

## Modes: demo vs live

| | Demo mode (default) | Live mode |
|---|---|---|
| Planner / LLM | Deterministic rule-based planner emitting `search_products` / `get_store_availability` tool calls and grounded summaries | OpenAI Responses API, strict function calling, at most 3 tool rounds per turn |
| Speech-to-text | Browser `SpeechRecognition` (Chrome, Safari) or typed input | ElevenLabs Scribe v2 realtime over WebSocket; server-side VAD decides when to commit |
| Text-to-speech | Browser `speechSynthesis` | ElevenLabs streaming TTS (MP3 or PCM) relayed as binary WebSocket frames |
| Image enrichment | Checked-in attribute fixture, labelled `fixture` | OpenAI vision via Responses API `input_image`, strict JSON schema |

To go live: Admin → Settings → Providers → save both keys → *Test connection* → Models & voice → pick a voice → turn **Mock mode** off → Save. Shoppers with an open page pick up the new capabilities on their next session; an in-flight turn never mixes old and new credentials.

---

## Architecture

```
Browser ──WS /ws/voice (PCM16 16 kHz in; JSON events + audio frames out)──▶ FastAPI gateway
  │  AudioWorklet capture · MediaSource/PCM playback · Orb + Waveform driven by real levels
  └─HTTP /api/v1 ── sessions · typed messages · products · variants · location consent · admin

Gateway ─▶ EnergyVAD + TurnDetector (750 ms silence, 200 ms min speech, 10 s no-speech, 20 s max utterance)
        ─▶ ElevenLabs STT (manual commit on endpoint)
        ─▶ AgentController: ONE bounded tool loop, shared by voice and typed turns
             ├─ search_products ─▶ QueryRouter: exact model | attribute filters | text
             │                     → top-20 candidates → ONE batched inventory query → 3–5 cards (+ labelled alternatives)
             └─ get_store_availability ─▶ direct (variant, store) read; distance sort only with a consented location token
        ─▶ ElevenLabs TTS stream ─▶ browser (barge-in cancels stale audio)

Offline: enrichment worker ─ idempotent on (image group, image hash, model version), backoff, dead-letter, review queue
         ─▶ enriched_attributes ─▶ search index rebuild
```

Design rules that the code enforces:

1. **One controller, specialised retrieval paths.** The LLM sees two small tools; the backend routes deterministically and never lets the model write queries.
2. **Search never claims stock.** Only a variant-level inventory read can mark something in stock. Inventory failures surface as *Availability temporarily unavailable*, never *In stock*.
3. **Enrichment is offline.** Customer turns only touch indexed attributes.
4. **Demo mode is honest.** Mock outputs are labelled; the fixture never pretends to be a real vision model.
5. **Secrets stay server-side**, versioned so key changes invalidate provider clients safely.

Session memory holds structured preferences, the selected variant, the last shown cards, the last 10 messages and a location token. Merging is validated: explicit values override, nulls leave values intact. Topic shifts reset stale filters: a new `MODEL-xxx` drops earlier brand/colour/category filters, and a fresh use-case sentence with no other filters starts a new need (size is kept).

See `docs/architecture.md` and `docs/api-contract.md` for the full event protocol and endpoint list.

---

## Configuration

All backend settings are environment variables (see `.env.example`). Settings saved in Admin override environment fallbacks for provider keys.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./shoescout.db` | SQLAlchemy async URL; Postgres via `postgresql+asyncpg://…` |
| `ELASTICSEARCH_URL` | unset | When set, the Elasticsearch adapter replaces the in-memory index (versioned index + alias swap) |
| `REDIS_URL` | unset | When set, sessions are stored in Redis with TTL |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS and WebSocket origin allow-list |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` | unset | Server-side fallbacks; Settings-stored keys take precedence |
| `CREDENTIALS_ENCRYPTION_KEY_B64` | dev: auto-generated file | 32-byte AES-GCM master key, base64. **Required in production** |
| `ADMIN_AUTH_SECRET` | dev: derived | Signs the admin session cookie. **Required in production** |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | `admin` / unset | Argon2id hash from `python -m scripts.hash_password <pw>` |
| `ADMIN_PASSWORD` | unset | Local development only; hashed at startup |
| `DEFAULT_*_MODEL`, `DEFAULT_ELEVENLABS_VOICE_ID`, `DEFAULT_CURRENCY` | see example | Initial non-secret settings (editable in Admin) |
| `MOCK_MODE` | `true` | Initial mock-mode flag (editable in Admin) |
| `SEED_ON_STARTUP` | `true` | Seed the demo catalogue if the database is empty |
| `RUN_WORKER` | `true` | Run the enrichment worker inside the API process (set `false` when a dedicated worker runs) |

Frontend: `NEXT_PUBLIC_API_BASE` (public, non-secret) is the only variable.

Generate production secrets:

```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"   # CREDENTIALS_ENCRYPTION_KEY_B64
cd backend && .venv/bin/python -m scripts.hash_password 'your-admin-password'      # ADMIN_PASSWORD_HASH
```

---

## Running with Docker Compose

Starts Postgres, Redis, Elasticsearch, the API, a dedicated enrichment worker and the web app.

```bash
cp .env.example .env
# set ADMIN_PASSWORD_HASH, CREDENTIALS_ENCRYPTION_KEY_B64, ADMIN_AUTH_SECRET in .env
docker compose up --build
```

Web: http://localhost:3000, API: http://localhost:8000 (`/api/docs` for OpenAPI). The same application code runs against SQLite/in-memory in development and Postgres/Elasticsearch/Redis in Compose; adapters are chosen purely by the URL variables above.

---

## Tests

```bash
# Backend (37 tests): endpointing state machine, VAD, query router, agent memory flows (T01–T08, T13–T17),
# WebSocket gateway, enrichment idempotency, secret encryption, admin auth
cd backend && .venv/bin/python -m pytest -q

# End-to-end (10 tests, desktop + mobile): typed search and context, details sheet and store availability,
# voice button with a fake microphone, admin login, key save/mask/remove, no-secret-leak checks
cd frontend
pnpm exec playwright install chromium
NEXT_PUBLIC_API_BASE=http://localhost:8000 E2E_ADMIN_PASSWORD=<your ADMIN_PASSWORD> pnpm exec playwright test

# Static checks
cd frontend && npx tsc --noEmit && npx eslint . && pnpm build
```

The e2e suite expects the backend and frontend to be running. Real provider calls are exercised only through *Test connection* in Settings when keys are configured.

`docs/evaluation-cases.json` lists the PRD acceptance scenarios T01–T20 and which behaviour each asserts.

---

## Security model

- **Provider keys**: submitted once over HTTPS to the authenticated admin API, validated, AES-GCM encrypted with a server-held master key (AAD = provider name), stored as ciphertext + nonce + fingerprint + last4. Read APIs return `configured`, `source` (`settings` / `environment`) and `last4` only. Keys never appear in `NEXT_PUBLIC_*`, WebSocket frames, URLs, logs or error messages (error text is redacted).
- **Config versioning**: saving or removing a key bumps `config_version`; provider clients are cached per version, so a turn that started under the old configuration finishes with it and never mixes credentials.
- **Admin auth**: Argon2id password, signed HttpOnly SameSite=Lax cookie (Secure over HTTPS), CSRF header required on every mutation, login limited to 10 failed attempts per 5 minutes per IP, audit log without secret values. Production SSO/OIDC can replace this adapter.
- **Shoppers**: anonymous sessions with TTL, per-IP rate limits on session creation and messages, no key submission path.
- **Location privacy**: geolocation is requested only after an explicit click; the server issues an opaque short-lived `location_token`; raw coordinates never enter LLM prompts or session reads.
- **Prompt injection**: catalogue text is declared untrusted data in the system prompt and the vision instructions; tool arguments are validated against strict schemas and unknown tools are rejected.
- **SSRF**: enrichment fetches only relative demo images or allow-listed hosts.
- **Transport**: CORS and WebSocket origin allow-list, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` on API responses.

Deploy the frontend and API on the same site (same registrable domain, or behind one reverse proxy) so the Lax admin cookie is sent with API calls.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Home page shows "Can't reach the ShoeScout API" | Backend not running, or `NEXT_PUBLIC_API_BASE` points at the wrong port. Restart `pnpm dev` after changing `.env.local`. |
| "Session expired, reconnecting…" flashes after a backend restart | Expected: in-memory sessions are lost on restart; the page creates a new session automatically and re-sends the message you had just typed. Set `REDIS_URL` to persist sessions across restarts. |
| *Start talking* says server speech recognition is not configured | You are in demo mode. Chrome and Safari fall back to the browser's recognition; Firefox has none, so type instead. Save an ElevenLabs key and voice ID for server speech. |
| No audio in live mode | A voice ID is required; pick one in Models & voice. `tts.unavailable` with `no_voice_id` is sent to the client in this case. |
| Admin login says "Too many login attempts" | 10 failed attempts within 5 minutes from your IP. Wait, or restart the backend (the counter is in memory). |
| Admin login says admin is not configured | Set `ADMIN_PASSWORD_HASH` (or `ADMIN_PASSWORD` locally) and restart the backend. |
| Orb looks like flat soft petals | That is the current ElevenLabs Orb design in this registry version. Its noise texture is vendored at `frontend/public/perlin-noise.png`. |
| `pnpm` cannot reach the registry | Corporate mirrors may block it: `npm_config_registry=https://registry.npmjs.org/ pnpm install`. |

---

## Known limitations and roadmap

Shipped (P0): responsive storefront, voice and typed turns through one controller, server VAD endpointing, session memory, exact/attribute/text routing, batched stock verification, labelled alternatives, store lookup with consented location, offline enrichment with review queue, encrypted admin-configurable providers, mock mode, unit/integration/e2e tests, Docker Compose.

Not yet (P1): semantic/vector retrieval, Silero/WebRTC VAD (the energy VAD sits behind the same interface), streaming LLM→TTS chunking, map view, saved favourites, multilingual tuning, load testing, SSO. Barge-in stops stale playback and supersedes the turn, but a partially streamed LLM answer is not retried. Live mode has not been exercised against real OpenAI/ElevenLabs accounts in this repository; the adapters follow the documented wire protocols and *Test connection* is the first thing to run with real keys.

All products, prices, stock and stores are fictional. Brand names appear only so natural queries work in the demo.

---

## Repository layout

```
ShoeScout/
├── README.md · PRD.md · docker-compose.yml · Makefile · .env.example
├── docs/            architecture.md · api-contract.md · evaluation-cases.json
├── backend/         FastAPI (Python 3.12)
│   ├── app/main.py                     app factory, lifespan (init DB, seed, index, worker)
│   ├── app/api/{sessions,products,admin}.py
│   ├── app/ws/voice_gateway.py         app-owned WebSocket protocol
│   ├── app/voice/{vad,turn_detector,audio_formats}.py
│   ├── app/agent/{controller,prompt,tools,state}.py
│   ├── app/providers/{openai_llm,openai_vision,elevenlabs_stt,elevenlabs_tts,mock,factory}.py
│   ├── app/search/{index,elastic,router,normalize}.py
│   ├── app/inventory/{service,location}.py
│   ├── app/enrichment/worker.py
│   ├── app/security/{auth,secrets}.py
│   ├── app/seed/{demo_catalog,seed}.py
│   ├── scripts/{seed_demo,hash_password,worker}.py
│   └── tests/
└── frontend/        Next.js 16 · TypeScript · Tailwind 4 · shadcn/ui · ElevenLabs UI
    ├── app/page.tsx · app/products/[id]/page.tsx · app/admin/{login,settings}/page.tsx
    ├── components/ui/                 vendored shadcn + ElevenLabs UI registry sources
    ├── components/voice/{VoiceAssistant.tsx,VoiceSessionManager.ts,AudioCapture.ts,AudioPlayback.ts}
    ├── components/products/{ProductCard,ProductGrid,ProductDetail,StoreList,LocationPrompt}.tsx
    ├── components/admin/ProviderSettingsForm.tsx
    ├── hooks/ · lib/api.ts · public/worklets/pcm-processor.js
    └── tests/ (Playwright)
```
