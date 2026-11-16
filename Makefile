.PHONY: up down install migrate run-api run-ui dev check build smoke test

up:
	docker compose up -d --wait

down:
	docker compose down

install:
	cd backend && uv sync
	cd frontend && npm ci

migrate:
	cd backend && uv run alembic upgrade head

run-api:
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

run-ui:
	cd frontend && npm run dev

dev:
	@echo "启动后端 (:8000) / 前端 (:5173)，Ctrl-C 退出"
	$(MAKE) -j2 run-api run-ui

check:
	cd backend && uv run ruff check
	cd backend && uv run ty check
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

smoke:
	cd backend && uv run python scripts/smoke_chat.py

test: check
