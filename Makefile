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

test:
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
	@echo "Nothing to do yet: docker-compose.yml lands in roadmap item 0.4."

db-down:
	@echo "Nothing to do yet: docker-compose.yml lands in roadmap item 0.4."

model-up:
	@echo "Nothing to do yet: the local model client lands in roadmap item 4.3a."

migrate:
	@echo "Nothing to do yet: the migration runner lands in roadmap item 1.1."

ingest:
	@echo "Nothing to do yet: the ingestion pipeline lands in roadmap item 2.5."

dev:
	@echo "Nothing to do yet: the API lands in roadmap item 5.1, the frontend in 6.1."
