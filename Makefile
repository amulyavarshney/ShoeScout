.PHONY: setup backend frontend dev test test-backend test-e2e seed hash-password up down

BACKEND_PORT ?= 8000

setup:
	cd backend && uv venv .venv -p 3.12 && uv pip install -p .venv/bin/python -r requirements.txt
	cd frontend && pnpm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port $(BACKEND_PORT)

frontend:
	cd frontend && pnpm dev

seed:
	cd backend && .venv/bin/python -m scripts.seed_demo --force

hash-password:
	cd backend && .venv/bin/python -m scripts.hash_password "$(PASSWORD)"

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-e2e:
	cd frontend && pnpm exec playwright test

test: test-backend test-e2e

up:
	docker compose up --build

down:
	docker compose down
