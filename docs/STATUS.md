# STATUS

The only file that carries state between sessions. Claude Code reads it at session start
and updates it at the end of every unit.

It records what exists, not what is scheduled. There are no dates in this file except in
Findings, where a measurement is only meaningful with the date it was taken.

Keep it short. If it grows past two screens, the Decisions section has turned into a
changelog and should be trimmed to the decisions that still constrain future work.

---

## What exists

**Environment and skeleton (0.1, 0.2, 0.6).**

- Git repository on `main`, with a `.gitignore` covering Python, Node, tool caches, model
  caches, and `.env` (but not `.env.example`). Placeholder `README.md`, rewritten in 8.5.
- `backend/` is an installable package, `portfolio_bot`, on Python 3.12 managed by `uv`.
  Dev tooling only: pytest, pytest-asyncio, ruff, mypy. No runtime dependencies yet.
- `pb` console script exists and dispatches. Every subcommand prints that it is not
  implemented and names the roadmap item that will implement it.
- `Makefile` has all nine targets from the CLAUDE.md table. `setup`, `test`, and `lint`
  do real work. The rest print why they have nothing to do and exit 0.
- 10 tests, all passing. `make lint` clean (ruff check, ruff format, mypy strict).

**Environment and skeleton (0.3, 0.4, 0.5).**

- `Settings` in `settings.py` holds every tunable value, read from the environment and
  the repo-root `.env`. `DATABASE_URL` and `MODEL_API_KEY` have no defaults, so a missing
  one fails at startup. `get_settings()` is cached, so the environment is read once.
- `docker-compose.yml` runs `pgvector/pgvector:pg16` with a healthcheck and a named
  volume. `make db-up` waits for healthy; `make db-down` keeps the data.
- `.env.example` documents every name. `make setup` copies it to `.env` when missing and
  says what to fill in. `make db-up` refuses to run against an unfilled `.env`.
- Logging configured once in `logging_config.py`, human-readable or JSON per
  `LOG_FORMAT`, level per `LOG_LEVEL`. Every module gets its logger from `get_logger`.
- 35 tests. No test touches Postgres yet; that starts with the fixtures in 1.5.

Phase 0 is complete.

**Database and migrations (1.1, 1.2).**

- `backend/migrations/` holds numbered `.sql` files. `0001_initial.sql` creates the
  `vector` extension and three tables: `documents` (one per markdown file, with a
  content hash so re-ingestion can skip unchanged files), `chunks` (one per slice, with
  character offsets and a `text[]` heading path, cascading from its document), and
  `chunk_embeddings` (one per chunk, `vector(384)`, with the model name and revision that
  produced it). No indexes yet; those are 1.4.
- `db/migrate.py` discovers migrations by numeric prefix, records applied ones with a
  SHA-256 checksum in `schema_migrations`, and applies each pending file in a transaction
  that also writes its bookkeeping row, so a failure leaves neither. It opens its own
  connection, not the pool. Editing a committed migration is refused at the next run.
- `pb migrate` and `make migrate` do real work. `make migrate` twice on an empty database
  gives `applied 1 migration` then `no pending migrations`.
- Tests marked `database` create a randomly named throwaway database, run every migration
  into it, and drop it. They skip with a readable message when Postgres is unreachable,
  and `make test` warns first so a half-run suite cannot look clean.
- 57 tests, 8 of them against real Postgres. `make lint` clean.

As things get built, one line each, grouped loosely by roadmap area. This is the section
a fresh session actually needs, so write it for someone who has read nothing else.

## In progress

Work that is started and not finished. Anything can sit here indefinitely; a stale entry
is not a problem to solve, it is a thing that was set down.

| Item | Where it stopped | Branch |
|---|---|---|
| none yet | | |

## Decisions

One line each. What was chosen, and the reason in a clause. No separate files, no
history. A decision that gets reversed is edited here, with the reversal noted inline.

| Id | Decision | Why |
|---|---|---|
| D1 | Postgres 16 with pgvector as the only store | One system for rows and vectors; no second service to run or deploy |
| D2 | psycopg3 with hand-written SQL, no ORM | The SQL and the indexing are things worth being able to explain |
| D3 | `BAAI/bge-small-en-v1.5`, 384-dim, run locally | Free, fast enough on CPU, small vectors keep the HNSW index cheap |
| D4 | FastAPI backend, Next.js frontend, separate services | Streaming and a retrieval-inspection UI need real client state |
| D5 | Server-Sent Events for streaming, not WebSockets | One-directional; SSE is simpler and survives proxies better |
| D6 | Open-weight models only for generation, behind one OpenAI-compatible client | Shows experience with open models alongside closed ones; the shared interface makes model swaps configuration |
| D6a | `qwen3.5:9b` on Ollama in development, `llama-3.3-70b-instruct` hosted in production | Local is free and offline while iterating on prompts; the 70B is stronger at instruction-following, which is what the refusal behavior depends on, and costs under a dollar a month at portfolio traffic |
| D6b | Model weights not self-hosted in production | A CPU machine large enough to serve 9B costs more per month than the hosted endpoint costs per year. Revisit only if serving it personally is worth paying for |
| D7 | No UI work required before retrieval works | Retrieval quality is measurable from a CLI; a chat box is a slow way to tune it |
| D8 | Corpus is markdown in git, no CMS | The content is Tae's writing and changes rarely |
| D9 | Lexical arm starts as Postgres FTS, hand-written BM25 deferred to 8.2 | Ships in an afternoon rather than a week; the two stay comparable behind one interface |
| D10 | The roadmap is an inventory, not a schedule | Fixed phase order and per-phase gates were the thing that made the previous setup unusable |
| D11 | Backend Python is uv-managed 3.12, pinned in `backend/.python-version`, `uv.lock` committed | Leaves the system Python alone, and an application wants a reproducible lock |
| D12 | Runtime dependencies are declared by the unit that first needs them; dev tooling declared up front | Keeps the dependency list an honest record of what the code actually imports |
| D13 | `pb` uses stdlib argparse until 2.5 | The stack table names no CLI library, and 2.5 is where real flags first exist |
| D14 | ruff at line length 100 with `E,F,I,UP,B,SIM`; mypy strict on `src`, relaxed on `tests` | One config in `pyproject.toml`, strict where the shipped code is |
| D15 | Makefile stays compatible with GNU Make 3.81 | The version macOS ships, so nobody has to install a newer make to build this |
| D16 | `MODEL_API_KEY` is required; local development sets it to a placeholder | Keeps 0.3's startup check, which is what stops a production deploy with no key. Ollama discards whatever it is sent |
| D17 | `LOG_FORMAT` (`console` or `json`) selects the log format, not an `app_env` setting | Names what it controls, instead of an environment concept that quietly grows other behavior |
| D18 | `.env` carries both the `POSTGRES_*` parts and a full `DATABASE_URL` | Compose needs the parts, the app needs a URL, and production hands over only a URL. The duplication is local-only and documented in `.env.example` |
| D19 | `make setup` creates `.env` from `.env.example` but never invents values | Secrets stay out of tracked files; `make db-up` guards against an unfilled `.env` rather than failing inside Docker |
| D20 | The migration runner opens its own connection, not the 1.3 pool | A pool amortizes setup across many short concurrent requests; a migration run is one sequential job that has to work before the application is wired up |
| D21 | `schema_migrations` stores a SHA-256 of each applied file | Hard rule 6 forbids editing a committed migration but nothing detected it. A checksum mismatch stops the run instead of letting fresh and existing databases drift apart |
| D22 | `chunks.heading_path` is `text[]`, not a joined string | The innermost heading and "everything under heading X" stay direct queries; joining for display is one line, splitting back is lossy |
| D23 | `database`-marked tests skip when Postgres is unreachable, and `make test` warns when the container is down | A fresh clone should not look broken before `make db-up`; the warning is what stops a half-run suite from reading as a clean pass |

## Open items

Things found mid-unit that were out of scope at the time. Not a feature backlog, only
things noticed while doing something else that would otherwise be lost.

| Item | Where it belongs |
|---|---|
| No LICENSE file. Not requested anywhere in the roadmap | 0.1 or 8.5 |
| Chunking constants (1000 and 150 characters) are conventional starting values, not measured ones | 3.6 |
| Nothing enforces that `DATABASE_URL` and the `POSTGRES_*` values in `.env` agree | 0.4, if drift ever bites |
| The throwaway-database fixture lives in `test_migrate.py` and derives a maintenance URL by swapping the database name in `DATABASE_URL`. It should move to `conftest.py` | 1.5, which is expected to replace it |
| Nothing rolls a migration back. Forward-only is fine for now; there is no `pb migrate --down` | Not requested anywhere; raise if it ever matters |

## Findings

Measurements and results that later decisions depend on. Dated, because a measurement
without a date cannot be compared to a later one.

A finding that contradicts a decision above gets written here first and the decision
edited second, never the reverse.

**2026-08-17, environment verification.** Checked before Phase 0 work, because three
stack choices were unconfirmed on this machine.

- `pgvector/pgvector:pg16` publishes a native `linux/arm64` image, so local Postgres runs
  without emulation on Apple silicon.
- The Ollama tag `qwen3.5:9b` from D6a exists in the registry, so `make model-up` is
  buildable as written.
- `BAAI/bge-small-en-v1.5` is at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`
  (last modified 2024-02-22). This is the string to pin in 0.3.
- Toolchain: Docker Desktop 29.7.2 (aarch64, Compose v5.4.0), uv 0.9.6, Python 3.12.12
  installed by uv. System Python 3.11.7 left untouched.
