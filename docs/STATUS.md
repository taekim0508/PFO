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

Not built yet in this area: settings module (0.3), Docker Postgres (0.4), logging (0.5).

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

## Open items

Things found mid-unit that were out of scope at the time. Not a feature backlog, only
things noticed while doing something else that would otherwise be lost.

| Item | Where it belongs |
|---|---|
| `MODEL_API_KEY` is meant to fail at startup when missing, but Ollama in development needs no key | 0.3 |
| Undecided whether `make setup` creates `.env` from `.env.example`, or `make db-up` fails until it exists | 0.3 with 0.6 |
| Local Postgres database name, user, password, and host port not chosen | 0.4 |
| No default values chosen yet for chunk size, chunk overlap, top-k, or the RRF constant | 0.3 |
| Nothing selects the production log format; the 0.3 settings list has no environment setting | 0.5 |
| No LICENSE file. Not requested anywhere in the roadmap | 0.1 or 8.5 |

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
