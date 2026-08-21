# Every target in the CLAUDE.md command table. Targets whose work does not exist yet
# print the reason and exit 0, so the table and this file stay in sync from the start.
#
# Kept compatible with GNU Make 3.81, the version macOS ships.

BACKEND := backend
UV := uv

.DEFAULT_GOAL := help
.PHONY: help setup db-up db-down model-up migrate ingest dev test lint

help:
	@echo "Targets:"
	@echo "  setup      Install Python and Node dependencies"
	@echo "  db-up      Start Postgres with pgvector in Docker"
	@echo "  db-down    Stop it"
	@echo "  model-up   Pull and serve the local model with Ollama"
	@echo "  migrate    Apply pending migrations"
	@echo "  ingest     Chunk, embed, and index everything in content/"
	@echo "  dev        Run the API and the frontend together"
	@echo "  test       Backend and frontend tests"
	@echo "  lint       ruff, eslint, prettier, type checks"

setup:
	@echo "==> Python dependencies"
	cd $(BACKEND) && $(UV) sync
	@echo "==> Node dependencies skipped: frontend/ does not exist yet (roadmap 6.1)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "==> Created .env from .env.example."; \
		echo "    Fill in POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT,"; \
		echo "    DATABASE_URL, and MODEL_API_KEY before running make db-up."; \
	else \
		echo "==> .env already exists, left alone"; \
	fi

test:
	@# Tests marked `database` skip themselves when Postgres is unreachable, which would
	@# otherwise let a suite that ran half of itself look like a clean pass. Say so first.
	@if ! docker compose ps --status running --services 2>/dev/null | grep -q '^db$$'; then \
		echo "==> WARNING: Postgres is not running, so database tests will be skipped."; \
		echo "    Run 'make db-up' to run the whole suite."; \
	fi
	@echo "==> Backend tests"
	cd $(BACKEND) && $(UV) run pytest
	@echo "==> Frontend tests skipped: frontend/ does not exist yet (roadmap 6.1)"

lint:
	@echo "==> ruff check"
	cd $(BACKEND) && $(UV) run ruff check .
	@echo "==> ruff format --check"
	cd $(BACKEND) && $(UV) run ruff format --check .
	@echo "==> mypy"
	cd $(BACKEND) && $(UV) run mypy
	@echo "==> eslint and prettier skipped: frontend/ does not exist yet (roadmap 6.1)"

db-up:
	@if [ ! -f .env ]; then \
		echo "No .env found. Run 'make setup' first, then fill it in."; \
		exit 1; \
	fi
	@if ! grep -qE '^POSTGRES_PASSWORD=.+' .env; then \
		echo "POSTGRES_PASSWORD is empty in .env. Fill it in before starting Postgres."; \
		exit 1; \
	fi
	docker compose up -d --wait
	@echo "==> Postgres is up and reporting healthy"

db-down:
	docker compose down
	@echo "==> Stopped. The data volume is kept. 'docker compose down -v' also erases it."

model-up:
	@echo "Nothing to do yet: the local model client lands in roadmap item 4.3a."

migrate:
	cd $(BACKEND) && $(UV) run pb migrate

ingest:
	@echo "Nothing to do yet: the ingestion pipeline lands in roadmap item 2.5."

dev:
	@echo "Nothing to do yet: the API lands in roadmap item 5.1, the frontend in 6.1."
