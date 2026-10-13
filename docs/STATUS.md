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
  produced it). Indexes are in 0002 rather than here.
- `db/migrate.py` discovers migrations by numeric prefix, records applied ones with a
  SHA-256 checksum in `schema_migrations`, and applies each pending file in a transaction
  that also writes its bookkeeping row, so a failure leaves neither. It opens its own
  connection, not the pool. Editing a committed migration is refused at the next run.
- `pb migrate` and `make migrate` do real work. `make migrate` twice on an empty database
  gives `applied 1 migration` then `no pending migrations`.
- Tests marked `database` never touch the developer's database. They skip with a readable
  message when Postgres is unreachable, and `make test` warns first so a half-run suite
  cannot look clean. The fixtures that build their databases are described under 1.5.
- 57 tests, 8 of them against real Postgres. `make lint` clean.

**Database and migrations (1.4).**

- `0002_indexes.sql` adds the two indexes retrieval needs: an HNSW index on
  `chunk_embeddings.embedding` with `vector_cosine_ops` and explicit `m` and
  `ef_construction`, and a GIN index on `to_tsvector('english', text)` over `chunks` for
  the lexical arm. Nothing else changed; the runner has no schema knowledge and did not
  need any.
- `make migrate` on a database at 0001 applies it and a second run reports nothing pending.
  `pg_indexes` for the two tables shows five indexes: the two new ones plus the three the
  primary keys and the unique constraint created in 0001.
- Three new tests. One checks the indexes exist. Two run `EXPLAIN` with `enable_seqscan`
  off and assert the planner reaches for each index, which is the check that catches an
  index that exists and is silently never used.
- 60 tests, 11 of them against real Postgres. `make lint` clean.

**Database and migrations (1.3).**

- `db/pool.py` is the only place the application opens a connection. `create_pool(url)`
  builds and opens a `psycopg_pool.ConnectionPool` for an explicit URL, `get_pool()` is the
  process-wide one built on first use from settings, `close_pool()` shuts it down and lets a
  later call build a fresh one.
- `connection()` lends a pooled connection; `transaction()` lends one with the block wrapped
  in an explicit transaction, which psycopg turns into a SAVEPOINT when nested. Both reuse
  the connection already in play via a `ContextVar`, so an inner block joins the outer
  transaction rather than opening a second one on a second connection.
- Rows come back keyed by column name, set once on the pool rather than per call site.
- The pool opens with `wait=True`, so a wrong URL or an unreachable server fails at startup
  instead of inside the first query. A failed open closes the pool before re-raising.
- `psycopg-pool` added as a runtime dependency; `uv.lock` regenerated. `db_pool_min_size`,
  `db_pool_max_size`, and `db_pool_timeout` added to settings and `.env.example`.
- Nothing calls the pool yet, so this unit adds no user-visible behavior. 1.5 and phase 2
  are what consume it.
- 71 tests, 21 of them against real Postgres. `make lint` clean.

**Database and migrations (1.5).**

- `tests/conftest.py` offers two kinds of database. `empty_database` is a throwaway with no
  tables, created and dropped per test, which is what the migration tests need because
  applying migrations is their subject. `migrated_database` is one database with every
  migration applied, built once for the whole run.
- `db` is the fixture everything from phase 2 on will use: a connection to
  `migrated_database` inside a transaction opened with `force_rollback`, so nothing a test
  writes is ever committed, whether the test passed or failed. Rows come back keyed by
  column name, matching what the pool hands production code.
- The local fixture in `test_migrate.py` is gone, and `test_pool.py` no longer imports
  across test modules. Both were open items.
- Pool tests keep a database per test. The pool opens its own connections, which are not
  inside the test's transaction, so the rollback would not cover what they write.
- 76 tests, 26 of them against real Postgres. `make lint` clean.

Phase 1 is complete.

**Continuous integration.**

- `.github/workflows/ci.yml` runs `make lint` then the backend suite on every push to
  `main` and every pull request. Postgres runs as a service container on the same
  `pgvector/pgvector:pg16` image compose uses, so the `database` tests execute rather than
  skip. `pytest -rs` names every skip, so a service container that failed to start cannot
  pass quietly. `uv sync --frozen` fails the build if `uv.lock` and `pyproject.toml`
  disagree.
- Verified green, verified red on a deliberately broken commit, and verified the eight
  database tests run in CI rather than skipping.
- README carries the CI badge.

**Corpus and ingestion (2.1, 2.2 to 2.5).**

- `content/` holds the corpus: eight first-person markdown files (about, education,
  skills and contact, the AI Producer internship, the lab research, Abroadly, FollowThru,
  this chatbot). `content/README.md` describes the expected shape and is not ingested.
- `ingest/loader.py` finds every `.md` under the content directory, requires front matter
  with a `title`, and fingerprints each file with SHA-256 of its raw bytes. Bytes are
  decoded without newline translation so character offsets stay true to the file.
- `ingest/chunker.py` cuts at headings, then splits an oversized section at blank lines,
  sentence ends, and finally a hard cut. Small pieces are packed back up to `chunk_size`,
  with up to `chunk_overlap` characters repeated from a word boundary within a section.
  Every chunk is exactly `text[char_start:char_end]` of the file and carries its heading
  path. Code fences are never split at their blank lines or sentences.
- `ingest/embedder.py` has the `Embedder` protocol, `SentenceTransformerEmbedder` (bge-small
  at the pinned revision, unit-normalized, model loaded on first use) and `FakeEmbedder`.
  Each chunk is embedded as `title > headings` followed by its text; the stored text is the
  file's text alone.
- `ingest/pipeline.py` writes each document in its own transaction and skips one whose hash
  matches and whose embeddings all come from the current model. A file gone from disk
  deletes its document by cascade. A broken file fails alone and keeps its stored version.
- `pb ingest` with `--path`, `--force`, `--dry-run`; `make ingest` runs it. Exit code 1 if
  any document failed.
- On the real corpus: 8 documents, 76 chunks, 76 embeddings. Second run: 0 processed.
  Editing one file re-processes exactly that file. Largest chunk 241 tokens, under the
  model's 512.
- `sentence-transformers` and `torch` added as runtime dependencies. On Linux, torch comes
  from PyTorch's CPU-only index.
- 123 tests, 1 skipped (the real-model test, which runs with `pytest --run-model` and was
  run and passed). `make lint` clean.

**Retrieval (3.1, 3.2, dense part of 3.5).**

- `retrieval/base.py` defines `RetrievalStrategy` (`name`, `retrieve(query, k)`), and
  `ScoredChunk`: a `RetrievedChunk` (text, document, heading path, offsets), a score, and
  a tuple of `Provenance(strategy, rank)` so fusion can record every contributing strategy.
- `retrieval/dense.py` has `DenseRetriever(conn, embedder, ef_search=...)`. It embeds the
  question with `embed_query`, which adds bge's query instruction, then orders by cosine
  distance and scores `1 - distance`. `hnsw.ef_search` is set per transaction. Only
  vectors from the embedder's own model and revision are ranked; others are skipped with a
  warning naming how many and which model.
- `Embedder.embed_query` added to the protocol and both embedders. `vector_literal` moved
  to `db/vector.py`, shared by ingest and retrieval.
- `pb search "query" [--strategy dense] [--k N]` prints rank, score, `title > headings`,
  and the chunk's first line of prose. `dense` is the only strategy so far.
- A conftest fixture restores the root logger after every test. `main()` was leaving a
  handler on a closed capture stream, which surfaced once a later test file logged.
- 146 tests, 2 skipped (both `--run-model`, run by hand and passing). `make lint` clean.

**Retrieval (3.3, lexical part of 3.5).**

- `retrieval/lexical.py` has `LexicalRetriever(conn)`: Postgres full-text search over chunk
  text, matching chunks that share any lexeme with the question, ranked by `ts_rank_cd`,
  ties broken by chunk id. Needs no embedding, so it finds chunks dense cannot.
- `retrieval/factory.py` has `build_strategy(name, conn, embedder, settings)` and
  `STRATEGY_NAMES`, the one place a name maps to a class. `pb search --strategy` takes its
  choices from there: `dense` or `lexical`.
- A test EXPLAINs the exact query that runs and asserts it can use `chunks_text_fts`;
  verified red by respelling the indexed expression.
- 164 tests, 2 skipped (`--run-model`). `make lint` clean.

**Retrieval (3.4, hybrid part of 3.5).**

- `retrieval/hybrid.py` has `reciprocal_rank_fusion(lists, rrf_k)`, a pure function, and
  `HybridRetriever(strategies, rrf_k=..., candidate_depth=...)`, which asks each strategy
  for `max(candidate_depth, k)` results, fuses them, and returns the top k. Provenance on
  a fused result carries every contributing strategy's own rank.
- The factory builds `hybrid` from dense and lexical. `HYBRID_CANDIDATE_DEPTH` (20) added
  to settings; `RRF_K` (60) was already there.
- `pb search` prints the rank as the position in its own list, scores to 4 decimals, and
  for hybrid each arm's rank after the location, e.g. `[dense 8, lexical 1]`.
- Fusion arithmetic is tested on hand-built lists against sums written out by hand.
- 184 tests, 2 skipped (`--run-model`). `make lint` clean.

Retrieval 3.1 to 3.5 are built. 3.6, the evaluation harness, is what says which is best.

**Retrieval evaluation (3.6, harness only).**

- `eval/retrieval.yaml` is the question set: each entry a `question`, one or more
  `expected` sections (`education.md > Degrees and dates`), and an optional `note`.
- `evaluation/questions.py` loads and checks it, reporting every problem at once by entry.
  `evaluation/metrics.py` has `recall_at_k`, `reciprocal_rank`, `precision_at_k`, pure
  functions over sections. `evaluation/runner.py` refuses an expected section no stored
  chunk lies under, then scores a strategy question by question.
- `pb eval run --strategy NAME [--k N] [--file F]` prints the first-hit rank or `miss` per
  question, then the averages. `pb eval compare` prints one row per strategy. `pb eval
  sections` lists every section in the form the file takes.
- PyYAML added as a runtime dependency, `types-pyyaml` as a dev one. `EVAL_SET_PATH` in
  settings. `eval/` added to the CLAUDE.md layout.
- 213 tests, 2 skipped (`--run-model`). `make lint` clean.

**Retrieval evaluation (3.6, question set and result).**

- `eval/retrieval.yaml` holds 106 questions, drafted by Claude Code and reviewed by Tae.
  Every content file is covered, including recruiter questions (projects, experience,
  degree, stack, leadership, location, start date, work authorization).
- 34 questions name Tae, and each is followed by a pronoun twin identical except for
  "he", "his", or "him", with the same expected sections. Six pairs also have a "you"
  twin. The notes mark which is which, so the pairs isolate what the name alone does.
- `content/job-search.md` added from Tae's own facts: roles sought, location and
  relocation, start date, work authorization. Its title leaves out the name on purpose.
  Corpus is now 9 documents, 79 chunks.
- `pb eval compare` result in Findings. Hybrid leads on every metric.
- The test asserting the committed eval file was empty now asserts it loads with at least
  thirty questions, the roadmap's minimum. 213 tests, 2 skipped (`--run-model`). `make lint`
  clean.

Retrieval 3.1 to 3.6 are built. Phase 3 is complete.

## In progress

Work that is started and not finished. Anything can sit here indefinitely; a stale entry
is not a problem to solve, it is a thing that was set down.

| Item | Where it stopped | Branch |
|---|---|---|
| Nothing in progress | | |

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
| D13 | `pb` uses stdlib argparse | The stack table names no CLI library. Revisited at 2.5, where real flags arrived: three flags did not justify a dependency |
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
| D24 | CI runs on push to `main` and on pull requests, not on pushes to other branches | A branch with an open PR would fire both events and run the same commit twice; a branch without one is work in progress |
| D25 | CI calls `pytest` directly rather than `make test` | `make test`'s Docker preflight has nothing to inspect in CI, where Postgres is a service container, and would print a false warning on every run |
| D26 | No standalone btree on `chunks.document_id` | The index behind `UNIQUE (document_id, ordinal)` already leads with that column, and Postgres uses a composite index for a leading-column prefix. A second one would find the same rows while taxing every chunk insert |
| D27 | Indexes are created with plain `CREATE INDEX`, not `CREATE INDEX CONCURRENTLY` | Concurrently avoids locking writes but cannot run inside a transaction, and the runner wraps every migration in one. Revisit the first time an index is added to a live table carrying traffic |
| D28 | The pool is a module global behind a `threading.Lock`, not an `lru_cache` | `lru_cache` can run its function twice when two threads race, and the loser's pool holds real connections with nothing left to close it. Uvicorn serves from a thread pool, so the race is live |
| D29 | `connection()` and `transaction()` reuse the connection already in play, tracked in a `ContextVar` | Nesting is the only thing `transaction()` adds over `connection()`, and it only works on one connection. Two connections would be two transactions, and the inner one could not see the outer one's uncommitted writes |
| D30 | The pool opens eagerly with `wait=True` | Matches 0.3's choice to fail at startup on missing configuration, rather than surfacing a bad URL inside whichever query runs first |
| D31 | `db_pool_max_size` defaults to 10 | Neon caps concurrent connections, and each uvicorn worker process gets its own pool, so the real ceiling is this number times the worker count |
| D32 | Two kinds of test database: `empty_database` per test, `migrated_database` once per run | Migration tests must start from nothing, since applying migrations is what they test. Everything else wants the tables already there and does not want to pay for building them per test |
| D33 | The `db` fixture rolls back unconditionally rather than relying on a connection's own rollback | A plain connection commits on success, so a *passing* test would be the one that leaves rows behind. Isolation cannot depend on the test failing |
| D34 | Pool tests keep a database per test instead of sharing `migrated_database` | The pool opens its own connections, which sit outside the test's transaction, so nothing it writes would roll back |
| D35 | Each chunk is embedded with its document title and heading path prepended; the stored text is the file's text alone | A mid-section chunk often never names its subject. Prepending context helps the vector without breaking the offsets citations depend on |
| D36 | A document is re-processed when its hash changes or any of its embeddings came from a different model or revision | Changing the embedding model would otherwise leave old and new vectors side by side, and they are not comparable |
| D37 | Chunking settings are not part of a file's fingerprint; changing them needs `pb ingest --force` | Folding them into the hash would make the stored hash stop meaning "the file's bytes" |
| D38 | On Linux, torch installs from PyTorch's CPU-only index | The default wheel bundles gigabytes of CUDA libraries the CPU-only embedder never uses, in CI and in the production image |
| D39 | The real embedding model is tested only under `pytest --run-model` | The default suite and CI never download a model; the one real-model test is run by hand when the embedder changes |
| D40 | Questions are embedded with bge's query instruction in front; chunks are not | The model was trained that way for short-question-to-passage search. It is a setting (`EMBEDDING_QUERY_INSTRUCTION`), so 3.6 can measure with and without |
| D41 | Dense search ranks only vectors from the running embedder's model and revision, and logs a warning naming any it skipped | Vectors from two models are not comparable; a missing chunk is visible and fixable, a chunk ranked on a meaningless score is neither |
| D42 | The effective `hnsw.ef_search` is the larger of the setting and k, capped at pgvector's 1000, and local to the query's transaction | The index cannot return more rows than its shortlist, so a smaller value would cut results short without error; transaction-local keeps it off later queries on a pooled connection |
| D43 | `ScoredChunk.provenance` is a tuple of `(strategy, rank)` | Fusion in 3.4 can record every strategy behind a result without changing the type |
| D44 | Lexical search matches any of the question's lexemes, not all of them | Requiring all returned nothing for five of five realistic questions on the real corpus (see Findings) |
| D45 | Strategies are built by name in one factory | `pb search`, 3.6, and the API choose strategies from strings; one mapping keeps them from drifting apart |
| D46 | Dense and lexical each search the whole corpus independently; fusion merges their lists rather than one filtering for the other | A filter can only drop chunks. On the real corpus each arm misses chunks the other finds, so either must be able to rescue one |
| D47 | Hybrid asks each arm for `max(HYBRID_CANDIDATE_DEPTH, k)` results, default 20, before fusing | Asking each for only k drops a chunk ranked just below the cut in one list before the other can lift it |
| D48 | Equal fused scores are broken by chunk id | Symmetric ranks (1st and 2nd against 2nd and 1st) tie exactly; any fixed rule beats an order that varies by run. Note it is arbitrary, not a judgment of which chunk is better |
| D49 | Eval answers are sections, not chunks, and a section covers everything beneath it | Chunk ids change on every ingest, and chunk size is one of the things 3.6 exists to compare; a section survives both |
| D50 | precision@k divides by k, not by how many results came back | A strategy returning two chunks for k=5 should not get perfect precision for getting both right |
| D51 | The bot speaks as a close friend answering on Tae's behalf, in the third person, not as Tae | Tae's call. Eval questions are mostly third person ("Tae", "he"), with a few "you" twins for visitors who address the bot as Tae anyway |

## Open items

Things found mid-unit that were out of scope at the time. Not a feature backlog, only
things noticed while doing something else that would otherwise be lost.

| Item | Where it belongs |
|---|---|
| No LICENSE file. Not requested anywhere in the roadmap | 0.1 or 8.5 |
| Chunking constants (1000 and 150 characters) are conventional starting values, not measured ones. Measurable now: `pb ingest --force` with other values, then `pb eval compare` | 8.x, or whenever retrieval is revisited |
| Nothing enforces that `DATABASE_URL` and the `POSTGRES_*` values in `.env` agree | 0.4, if drift ever bites |
| Nothing rolls a migration back. Forward-only is fine for now; there is no `pb migrate --down` | Not requested anywhere; raise if it ever matters |
| The GIN index covers `chunks.text` alone. Headings are searchable only where the chunk body repeats them | 3.2, if the lexical arm turns out to want them |
| `m` and `ef_construction` are pgvector's defaults, written out but never measured | 8.2, once there is a corpus to measure recall against |
| The pool exposes live statistics (connections in use, waiters, wait time). Nothing surfaces them, and "the bot is slow" and "the pool is exhausted" look identical from outside | 5.x, on a health endpoint |
| No statement timeout is configured on pooled connections, so one runaway query can hold a connection indefinitely | 5.x or 7.x, once there is real traffic |
| Front matter `tags` are accepted and ignored. The schema has no column for them and nothing uses them yet | 3.x, if filtering by tag is ever wanted |
| `transformers` prints a "Loading weights" progress bar on model load, which logging settings do not silence | Cosmetic; 8.x |
| The pool's "opened" and "closed" INFO lines print around every `pb search` result | Cosmetic; 8.x |
| The other-model check reads every row of `chunk_embeddings` on every search. Free at 76 rows, not at a much larger corpus | Move to once per process or into ingest if the corpus grows |
| Two chunks are a heading and nothing else (`Revisiting the project for this review`, `What I built: an explainable traffic signal controller`), produced when a heading is followed directly by subheadings. They are noise in every search | 2.3, the chunker |
| A question naming Tae is pulled toward `about.md`, whose title "About Tae Kim" is embedded with every chunk. Measured on 2026-10-12 (see Findings). Candidate fixes, none built: drop the title from `about.md`'s embedded text, retitle the file, or remove the name from the question before embedding it. The 34 twin pairs are the test for any of them | Its own unit, touching 2.4 or 3.2 |
| The corpus is first person ("I built") and the bot speaks in the third person (D51). Nothing yet says how generation turns one into the other | 4.x, the prompt |

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

**2026-08-20, a test that did not test what it claimed.** Proving CI turns red on a broken
commit involved deliberately changing the migration sort key from the parsed number to the
filename. CI stayed green. The filename pattern enforces a four-digit prefix, which makes
an alphabetical sort agree with a numeric one, so the old
`test_sorts_by_number_not_by_filename` could not fail. Renamed to state what it does prove,
with the real guarantee (the enforced width) named in both the test and the runner. The
deliberate-break check was redone against the filename pattern and did turn the build red.

**2026-08-26, the index tests were verified red.** A `pg_indexes` row proves an index
exists, not that anything uses it. Rebuilding the HNSW index with `vector_l2_ops` and
rerunning confirmed that `test_the_vector_index_serves_a_cosine_similarity_search` fails:
the plan falls back to a sort, because `<=>` is cosine distance and an L2 index cannot
serve it. Without the plan assertion that change would have passed the suite and quietly
disabled vector search. Separately, the first draft of the full-text test assumed the
English stemmer reduces "chunker" to "chunk". It does not; the corpus lexeme is `chunker`.
The test now uses "splits" against a query of "splitting", both of which reduce to `split`.

**2026-08-27, the connection-release test was verified red.** A test that borrows a
connection twice in sequence passes whether or not the first one was ever given back, if the
pool has spares. Capping the pool at one connection is what makes it meaningful. Confirmed
by rewriting `connection()` to take a connection with `getconn()` and never return it: the
second block blocked and failed with `PoolTimeout` after three seconds. Reverted after.

**2026-08-27, the rollback fixture was verified red.** A fixture that isolates nothing looks
identical to one that works, until a test reads a row it did not write. Replacing
`conn.transaction(force_rollback=True)` with a plain `conn.transaction()` made
`test_db_leaves_nothing_behind_for_the_next_test` fail, finding the document the previous
test had written. Note which direction that breaks in: with a plain transaction the earlier
test still passed, because its write is invisible to other connections while uncommitted.
It is the *passing* test that commits and pollutes. Reverted after.

**2026-10-09, a name in the question outweighs its subject.** On the real corpus, "Where did
Tae go to school?" ranks `about.md` chunks 1 to 5, with `Education > Degrees and dates`
8th. "Where did he go to school?" ranks that chunk 1st. "Tae's university and degree" also
misses it. Every `about.md` chunk is embedded with "About Tae Kim" in front (D35), so the
name in a question matches the title rather than the topic. Questions naming Tae are the
common case for this bot. Not fixed here: the lexical arm (3.3) should find "Vanderbilt" and
"degree" directly, and 3.6 is where the size of the effect gets measured. CI's first run
with torch (PR 8) took 1m26s in total, closing the open item on install time.

**2026-10-10, keyword matching needs any-word queries, and rewards common words.** Five
realistic questions run as all-words queries (`plainto_tsquery`) returned nothing, every
one: questions carry words like "go", "get", or "Tae" that rarely share a chunk ("tae"
appears in 1 of 76). As any-word queries they all return results. "Did Tae go to
Vanderbilt?" ranks `Education > Degrees and dates` 1st, and the Abroadly and chatbot
questions land on the right documents. "Where did Tae go to school?" still misses
Education, which never uses the word "school". `ts_rank_cd` counts matches without
weighting rare words, so most scores are 0.1 to 0.4 in steps of 0.1 and ties are common: a
match on "get" scores like a match on "vanderbilt". This is the gap BM25 (8.2) closes, and
a number for 3.6 to measure, not something to tune here.

**2026-10-10, fusion alone does not fix the name problem, and can undo a right answer.** A
script merging dense and lexical top-20 lists by RRF (k=60), ahead of 3.4, on three
questions about education. "Where did Tae go to school?": Education outside the fused top
6 (dense 6th and 8th, lexical none). "Where did he go to school?": Education 4th, down from
dense's 1st, because lexical matched "go" and "school" in unrelated chunks that then
appeared in both lists. "What degree did Tae get?": Education 5th. Fusion rewards
agreement, and here the two arms agreed on noise. Three questions are an anecdote, not a
measurement; this is the case for writing the 3.6 question set, with questions naming Tae
on purpose, before judging hybrid or any fix for the name.

**2026-10-10, hybrid in code matches the preview, and ties decide a top result.** `pb
search --strategy hybrid` gives the same rankings as the preview script above, so that
finding stands for the real implementation. New: "Did Tae go to Vanderbilt?" ties exactly
at 1st between `About Tae Kim` (dense 1, lexical 2) and `Education > Degrees and dates`
(dense 2, lexical 1), and D48's chunk-id rule puts About first. A rank-only fusion of two
arms produces exact ties whenever ranks mirror each other, so the order of the top answer
can rest on an arbitrary rule. Another number for 3.6, alongside BM25 and the name problem.

**2026-10-10, a red check can pass against stale bytecode.** Breaking `hybrid.py` with a
same-length edit, then restoring it within the same second, left Python's cached bytecode
looking current (it compares modification time and size), so the suite kept running the
broken version after the restore. Clear `__pycache__` after restoring a source file, or a
red check can produce false reds and, worse, false greens.

**2026-10-12, the evaluation table: hybrid leads, by a small margin.** `pb eval compare`
on 106 questions, k=5, the real corpus (9 documents, 79 chunks):

| strategy | recall@5 | MRR | precision@5 |
|---|---|---|---|
| dense | 0.772 | 0.646 | 0.238 |
| lexical | 0.621 | 0.522 | 0.181 |
| hybrid | 0.815 | 0.674 | 0.245 |

Hybrid beats dense by 0.043 recall and 0.028 MRR, roughly four or five questions out of
106. Lexical alone trails both. Precision is low for
every strategy because of the shape of the set, not the retrievers: most questions expect
one section of one or two chunks, so 0.2 to 0.4 is the ceiling there. Read precision only
as a comparison between rows.

**2026-10-12, the name costs dense search, and hybrid's lead comes mostly from repairing
it.** Splitting the same run by how the question refers to Tae (34 name questions, their
34 pronoun twins, 6 "you" twins, 32 others):

| strategy | name: recall / MRR | pronoun: recall / MRR | other: recall / MRR |
|---|---|---|---|
| dense | 0.662 / 0.521 | 0.806 / 0.758 | 0.875 / 0.682 |
| lexical | 0.635 / 0.552 | 0.635 / 0.552 | 0.641 / 0.485 |
| hybrid | 0.776 / 0.674 | 0.782 / 0.716 | 0.891 / 0.662 |

In dense, swapping "Tae" for "he" moves the right section up in 14 of 34 pairs and down
in 2. The reason: no chunk's text contains "Tae". Only the title "About Tae Kim" does, and
D35 embeds it with each of `about.md`'s five chunks, so the name pulls a question toward
those five whatever it asks. An earlier 12-question check put `about.md` in 45 of 60
dense top-5 slots when questions said "Tae", and 9 when they said "he". Lexical is
untouched: "he", "his", and "you" are stop words, and "tae" matches no chunk.

Hybrid closes most of the gap (7 pairs better with "he", 2 worse), and that is where most
of its overall lead comes from. On pronoun questions, dense alone is slightly better than
hybrid (MRR 0.758 against 0.716). So hybrid is the right default as things stand, but
partly because it compensates for a defect in what dense embeds. If the name problem is
fixed at the source, this comparison should be rerun before assuming hybrid still leads.
Six "you" twins are too few to conclude anything; in dense they mostly ranked with "he".

