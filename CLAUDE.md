# CLAUDE.md

Instructions for Claude Code working in this repository. Read this file completely at
the start of every session.

Every line here is meant to change what you do. If a rule stops doing that, delete it.

## What this project is

A personal portfolio site with an embedded RAG chatbot. The chatbot answers questions
about Tae's background, projects, and experience, grounded in a corpus of his own
writing. It is the centerpiece of the site, not a widget bolted onto it.

The site is a job-search artifact. It has to work, be public, and be explainable in an
interview. In that order.

## Stack

| Layer           | Choice                                                                                                                                                                                |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Language        | Python 3.12 (backend), TypeScript (frontend)                                                                                                                                          |
| Package manager | `uv` for Python, `npm` for Node                                                                                                                                                       |
| API             | FastAPI, served by uvicorn                                                                                                                                                            |
| Database        | Postgres 16 with the `pgvector` extension, Docker locally                                                                                                                             |
| DB access       | `psycopg3`, hand-written SQL, numbered `.sql` migrations. No ORM.                                                                                                                     |
| Embeddings      | `sentence-transformers`, `BAAI/bge-small-en-v1.5`, 384-dim, pinned by revision                                                                                                        |
| Generation      | Open-weight models only, behind one OpenAI-compatible client. `qwen3.5:9b` via Ollama in development, `llama-3.3-70b-instruct` on a hosted endpoint in production. Streamed over SSE. |
| Frontend        | Next.js App Router, React, TypeScript, Tailwind                                                                                                                                       |
| Tests           | `pytest` (backend), `vitest` (frontend)                                                                                                                                               |
| Lint/format     | `ruff` (backend), `eslint` + `prettier` (frontend)                                                                                                                                    |
| Hosting         | Vercel (frontend), Fly.io (backend), Neon (Postgres)                                                                                                                                  |
| Not used        | No LangChain, LlamaIndex, or any RAG framework. The pipeline is written directly.                                                                                                     |

Do not substitute any of these without asking. If one turns out to be the wrong choice
mid-build, say so and stop; do not swap it quietly.

The generation layer is deliberately provider-agnostic. Model name, base URL, and API
key are three settings, and swapping models is a config change, never a code change. Any
generation code that only works against one provider is a defect.

## Session start

Read these, in this order, before touching anything:

1. This file.
2. `docs/STATUS.md`: what exists, what is in progress, what has been decided.
3. `git log --oneline -15`.
4. The `How to use this file` section of `docs/ROADMAP.md`, plus the sections for
   whatever Tae says he is working on. Nothing else from it.

Do not read the roadmap end to end. Do not open source files you have no reason to
change. If `docs/STATUS.md` does not tell you enough to start, that is a defect in
`docs/STATUS.md`. Say so, and ask rather than guessing.

## Time, order, and scope

There is no schedule. No deadlines, no pace, no sense in which this project is behind.
Never ask about a timeline and never estimate one.

`docs/ROADMAP.md` is an inventory of the work this project contains, not a sequence. Its
phases are areas, numbered by rough dependency. There is no current phase. Finishing
something does not mean starting the next thing.

Tae brings a specific topic to each session. Settling how to split it is the first
conversation of that session, and it is a conversation, not a decision you make alone.
Two things drive the split:

- **A diff he can actually read.** If a unit would produce a diff too large to review
  carefully, propose a smaller first cut and say what it leaves out.
- **Tests that can still isolate a failure.** Migrations, schema changes, and wide
  refactors invalidate whatever a test loop was holding constant. Land them on their own,
  ahead of the behavior changes that depend on them, so a red test names one cause
  instead of three candidates.

The only ordering that binds is a real dependency. Everything else can be rearranged.

## How Tae works

One unit at a time, with a stated boundary, and nothing outside it gets touched. A unit
is whatever was agreed at the start of the session: one roadmap item, part of one, or
several across areas. Say the boundary back before planning it.

**Plan.** Files to create or change. Public signatures and what they return. How it is
tested and what the tests assert. Anything underspecified or any prerequisite that turns
out to be missing. Prose and lists, no code. Then stop and wait.

**Build.** After the go, write all of it: implementation, tests, wiring, config. No
permission file by file, no narration. If the work forces you outside the stated
boundary, stop and say so.

**Report.** What runs now and the command to run it. What differed from the plan and why.
Test results. What this unblocked. Then update `docs/STATUS.md` and commit.

## Communication

- No emojis. Anywhere. Code, comments, commit messages, docs, chat output, UI copy.
- No em dashes. Anywhere, same places. Use a comma, a colon, parentheses, or two
  sentences. This applies to prose you write into files as much as to chat.
- Tae has no prior AI/ML background. When a unit involves a concept he has not built
  before, add two or three sentences to the plan explaining the mechanism: what actually
  happens to the data, step by step. Not a definition, not a comparison to something
  else. Skip this for ordinary web and database work.
- Never claim something works without running it. "Tests pass" means you ran them.

## Hard rules

1. Do your best to prevent scope creep. Stay inside the agreed boundary; anything else
   you notice goes into the Open items section of `docs/STATUS.md`.

   Separately, and not as a substitute for that: when you see a place where more scope
   would materially improve the project or show strong engineering judgment to someone
   reviewing this repository, say so in the report. Name it, say roughly what it costs,
   and leave the decision to Tae. Do not build it, and do not raise the same suggestion
   twice.

2. Never invent a requirement. If the roadmap does not state it and Tae did not say it,
   ask. A guessed requirement becomes a feature nobody chose.
3. One commit per unit, on a branch named for what the unit does, not for where it sits
   in the roadmap (`rrf-fusion`, not `phase3`). A unit that spans areas is still one
   branch and one commit. The message says what changed and why, never how.
4. Secrets come from the environment, loaded through a settings module. No API keys,
   connection strings, or tokens in any git-tracked file, including tests, fixtures, and
   examples. `.env.example` holds names with empty values.
5. If a test fails, fix the code. Change a test only when the test itself is wrong, and
   say out loud that you are doing it and why.
6. Every schema change is a new numbered migration. Never edit a migration that has been
   committed.
7. Mock at the process boundary: the model endpoint, the filesystem, the clock. Never
   mock the thing under test, and never mock Postgres; tests run against a real throwaway
   database.
8. Config values a reasonable person would want to change (chunk size, overlap, top-k,
   fusion constant, model name) are named constants in one settings module, never
   literals scattered through call sites.

## Commands

Defined in the `Makefile`. Keep this table and the Makefile in sync.

| Command         | What it does                                     |
| --------------- | ------------------------------------------------ |
| `make setup`    | Install Python and Node dependencies             |
| `make db-up`    | Start Postgres with pgvector in Docker           |
| `make db-down`  | Stop it                                          |
| `make model-up` | Pull and serve the local model with Ollama       |
| `make migrate`  | Apply pending migrations                         |
| `make ingest`   | Chunk, embed, and index everything in `content/` |
| `make dev`      | Run the API and the frontend together            |
| `make test`     | Backend and frontend tests                       |
| `make lint`     | ruff, eslint, prettier, type checks              |

The backend also exposes a CLI, `pb`, used for everything before the API exists:
`pb ingest`, `pb search`, `pb ask`, `pb eval`. The Makefile targets wrap it. When working
on retrieval or generation, use `pb` directly rather than through `make`.

## Layout

```
.
|- CLAUDE.md
|- Makefile
|- docker-compose.yml
|- .env.example
|- content/                 corpus source, markdown, hand-written by Tae
|- docs/
|  |- ROADMAP.md            inventory of the work, grouped by area
|  |- STATUS.md             what exists, decisions, open items, findings
|- backend/
|  |- pyproject.toml
|  |- migrations/           numbered .sql files
|  |- src/portfolio_bot/
|  |- tests/
|- frontend/                Next.js app
```

## Where other things live

Interview preparation, study notes, and anything written for Tae rather than for the
project are outside this repository, in `~/Documents/Philipians413`. Nothing from there is
ever committed here. A hiring manager clones this repo; keep it to the engineering record.
