# ROADMAP

An inventory of the work this project contains, grouped by area.

This is not a schedule. It is not a plan with an order. It exists so that a fresh Claude
Code session does not have to be told what the project consists of, and so that no piece
of work gets forgotten because nobody wrote it down.

---

## How to use this file

**There are no dates and no deadlines.** Nothing here is due. There is no expected pace,
no sense in which the project is behind, and no correct number of items to finish in a
sitting. If a session is spent on one item and it is not finished, that is a normal
session. Never ask about or infer a timeline.

**Phases are areas of work, not steps.** They are numbered because dependencies run
roughly in that direction, not because they happen in that order. Phase 4 does not begin
when phase 3 ends. There is no such thing as being "on phase 3."

**Any amount of work is a valid unit.** Tae decides what a session covers. That might be:

- One item.
- Half of one item, with the rest another day.
- Three items from the same area.
- Items from two or three different areas at once, because they are related or because
  he feels like it.
- Something not listed here at all.

**Only the dependencies are binding.** Each area lists what genuinely has to exist first.
Those are real: you cannot write a chunk to a table that does not exist. Everything else
about the grouping is organizational convenience and can be rearranged freely.

**Items are an inventory, not a queue.** The identifiers (2.3, 5.1) are labels for
referring to things in conversation. They do not imply order, size, or that 2.3 takes as
long as 2.4. Some items are an hour and some are two days.

**Claude Code does not advance on its own.** Finishing an item does not mean starting the
next one. Report what is done, note what it unblocked, and stop. Tae picks what comes
next.

**"Worth not doing yet" is advice, not a rule.** Each area ends with a note on what is
tempting to pull in early and the reason waiting usually pays. If Tae wants to do it
anyway, do it. Say the reason once, then drop it.

---

## The areas

| # | Area | What it produces |
|---|---|---|
| 0 | Environment and skeleton | A repository where the tooling works |
| 1 | Database and migrations | A schema, applied repeatably |
| 2 | Corpus and ingestion | Content in the database, chunked and embedded |
| 3 | Retrieval | Ranked results, and a measurement of which ranking is best |
| 4 | Generation | Grounded, cited answers from the command line |
| 5 | HTTP API | Those answers streamed over the network |
| 6 | Frontend | A site that looks finished, with a working chat |
| 7 | Deployment | A public URL |
| 8 | Evaluation and polish | Numbers to defend, and a readable repository |

Generation uses open-weight models only, behind one OpenAI-compatible client. See the
stack table in `CLAUDE.md` and decisions D6, D6a, D6b in `docs/STATUS.md`.

The rough dependency direction is left to right, but it is rough. Frontend design work
(6.2) needs nothing. The corpus (2.1) is Tae's writing and can happen any time. Nothing
stops phase 0 tooling from being finished months after phase 3 is working.

---

## Phase 0: Environment and skeleton

**What this covers.** Making every command run. None of it is about RAG; the point is
that later work does not stop to fix tooling.

**Needs first.** Nothing.

### Work in this area

**0.1 Repository and git.**
Initialize on `main`. `.gitignore` covering Python bytecode, `.venv`, `.env`,
`node_modules`, `.next`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, and model caches.
Placeholder `README.md`, rewritten later in 8.5.

**0.2 Python toolchain.**
Install `uv`. `backend/pyproject.toml` targeting Python 3.12, project declared as a
package (`portfolio_bot`) so imports work without path hacks. Declare the `pb` console
script entry point now even though it does nothing. Dev dependencies: `pytest`,
`pytest-asyncio`, `ruff`, `mypy`, configured in `pyproject.toml` rather than in separate
files. Create `backend/src/portfolio_bot/__init__.py` and `backend/tests/`, plus one
trivial test asserting the package imports so `make test` has something to run.

**0.3 Settings module.**
`settings.py`. One `Settings` class loaded from environment variables via
`pydantic-settings`. Everything tunable in the project lives here from now on: database
URL, embedding model name and revision, chunk size, chunk overlap, top-k, RRF constant,
model name, model base URL, model API key, log level. Real defaults where a default is
sensible and none where it is not, so a missing `MODEL_API_KEY` fails at startup rather
than at first request. `.env.example` with every name and empty values.

The three model settings (name, base URL, key) are what make the generation layer
provider-agnostic. Ollama, Together, Groq, and Fireworks all speak the same
OpenAI-compatible shape, so switching between them is three environment variables.

**0.4 Docker Postgres.**
`docker-compose.yml`, one service on `pgvector/pgvector:pg16`, named volume, port
mapping, healthcheck on `pg_isready`. Credentials from `.env`.

**0.5 Logging.**
Configured once, level from settings, JSON in production and human-readable locally.
Every module gets its logger from here. Doing this early is what stops `print()` from
appearing in ingestion code and never leaving.

**0.6 Makefile.**
Every target in the CLAUDE.md command table, including `model-up`. Targets with nothing
to do yet print a line saying so and exit 0.

### What done looks like

- `make setup` completes from a clean clone.
- `make db-up` brings Postgres up and the healthcheck goes healthy.
- `make test` and `make lint` both pass.

### Worth not doing yet

Node and the Next.js scaffold. Generating them here means seven areas of work spent
looking at a directory of framework boilerplate nobody has touched, and `create-next-app`
is a five-minute command whenever it is actually wanted.

---

## Phase 1: Database and migrations

**What this covers.** The schema, a way to apply it repeatably, and a pooled connection
the rest of the code uses.

**Needs first.** 0.4 for a database to connect to. 0.3 for the URL to come from
somewhere. Both are small enough to fold into the same sitting as this work.

### Work in this area

**1.1 Migration runner.**
`db/migrate.py`. Reads `backend/migrations/*.sql` sorted by numeric prefix, tracks
applied ones in a `schema_migrations` table, applies each pending one in a transaction,
idempotent. Roughly eighty lines. No Alembic, because the schema is small and
hand-written SQL is the point.

**1.2 Schema.**
`0001_initial.sql`:

- `CREATE EXTENSION IF NOT EXISTS vector;`
- `documents`: id, source_path, title, content_hash, created_at, updated_at. Unique on
  source_path. The hash is what lets re-ingestion skip unchanged files.
- `chunks`: id, document_id (cascade delete), ordinal, text, token_count, heading_path,
  char_start, char_end, created_at. Unique on (document_id, ordinal).
- `chunk_embeddings`: chunk_id as primary and foreign key, embedding `vector(384)`,
  model_name, model_revision. Separate from `chunks` so re-embedding with a different
  model does not rewrite the text, and so a chunk can exist before it is embedded.

**1.3 Connection layer.**
`db/pool.py`. A `psycopg_pool.ConnectionPool` built once from settings, with context
managers for a connection and for a transaction, dict row factory. Nothing above this
layer constructs a connection.

**1.4 Indexes.**
`0002_indexes.sql`. HNSW on the embedding column with `vector_cosine_ops`, `m` and
`ef_construction` written explicitly rather than defaulted. GIN on a `tsvector`
expression over `chunks.text` for the lexical arm. Btree on `chunks.document_id`.

Separate from 1.2 on purpose: indexes are the thing most likely to change once there is
real data to measure, and a separate file makes that a normal migration rather than an
edit to committed history.

**1.5 Test fixtures.**
`conftest.py`. Session-scoped fixture creating a throwaway database and running every
migration against it. Function-scoped fixture wrapping each test in a transaction that
rolls back. Everything after this tests against real Postgres.

### What done looks like

- `make migrate` on an empty database creates every table and index, and a second run
  changes nothing.
- A test inserts a document, a chunk, and a 384-dim embedding and reads them back.
- `SELECT * FROM pg_indexes WHERE tablename IN ('chunks','chunk_embeddings');` shows the
  HNSW and GIN indexes.

### Worth not doing yet

Repository or data-access classes above the pool. There is no second caller yet, so the
abstraction would be shaped by guesses about what ingestion needs rather than by what it
turns out to need.

---

## Phase 2: Corpus and ingestion

**What this covers.** Getting Tae's writing into the database as chunks with embeddings,
without redoing work on files that have not changed.

**Needs first.** 1.2 and 1.3 for somewhere to write. 2.2 through 2.5 can all be built and
tested against fixture markdown before the real corpus exists, so 2.1 does not block
them.

### Work in this area

**2.1 Corpus.**
Tae writes the markdown. Claude Code writes `content/README.md` describing the expected
shape: front matter with `title` and `tags`, headings that mean something because
chunking uses them, one file per subject. A reasonable starting set is background, one
file per project, technical opinions, work history, education, and frequently asked
questions.

This is the one item Claude Code cannot do. It also gates the eval set in 3.6, and
through it every measurement in phases 3 and 8. Rough drafts unblock more than polished
ones.

**2.2 Document loader.**
Walks `content/`, parses front matter, computes a content hash, returns document records,
skips files whose hash matches what is stored. A deleted file removes its document and
chunks by cascade.

**2.3 Chunker.**
Recursive character splitting: split on `\n## `, then `\n\n`, then sentence boundaries,
then a hard character cut, descending only when a piece is still over the limit. Target
and overlap from settings. Every chunk carries its heading path and its character offsets
in the source, because those are what let a citation point at a real place in a real
file.

Tests assert exact boundaries on hand-written fixture text. Include the ugly cases: no
headings at all, a single paragraph longer than the limit, a document shorter than one
chunk, and a code fence that must not be split down the middle.

**2.4 Embedder.**
An `Embedder` protocol with `embed(texts: list[str]) -> list[list[float]]`. Two
implementations: `SentenceTransformerEmbedder` loading `BAAI/bge-small-en-v1.5` pinned to
an explicit revision and batching, and `FakeEmbedder` returning deterministic vectors
derived from a hash of the text. Every test not specifically about embedding uses the
fake, so the suite never downloads a model.

The real embedder normalizes to unit length at write time. On unit vectors cosine
similarity is a dot product, and pgvector's `<=>` then costs less. Worth a comment in the
code, because it is the kind of thing that gets asked about.

**2.5 Pipeline and CLI.**
Wires loader, chunker, and embedder, writing through the pool in one transaction per
document. `pb ingest` with `--path`, `--force`, `--dry-run`. Wire `make ingest` to it.

### What done looks like

- `make ingest` reports documents processed, chunks written, chunks embedded.
- A second run reports zero re-processed documents.
- Editing one file and re-running re-processes exactly that file.
- `SELECT count(*) FROM chunk_embeddings;` equals `SELECT count(*) FROM chunks;`.

### Worth not doing yet

Query-time embedding and any scoring. Ingestion is a write path and search is a read
path; building them together tends to produce one module that does both and is hard to
test.

---

## Phase 3: Retrieval

**What this covers.** Turning a question into ranked chunks, and measuring which way of
ranking is actually best rather than asserting it.

This is the area that decides whether the project is interesting. Everything before it is
plumbing and everything after it is presentation.

**Needs first.** 2.5, for something to search. 3.6 additionally needs 2.1, because an
eval set against fixture text measures nothing.

### Work in this area

**3.1 Retrieval interface.**
A `RetrievalStrategy` protocol: `retrieve(query: str, k: int) -> list[ScoredChunk]`.
`ScoredChunk` carries the chunk, a score, and a `provenance` field naming which strategy
produced it and at what rank. Provenance is what makes the inspection panel in 6.6
possible and costs nothing now.

**3.2 Dense retrieval.**
Embeds the query with the same embedder used at ingest, queries pgvector with `ORDER BY
embedding <=> %s LIMIT k`, converts distance to a similarity score. Set `hnsw.ef_search`
explicitly in the session rather than relying on the default.

**3.3 Lexical retrieval.**
Postgres full-text search over the GIN index from 1.4, ranked with `ts_rank_cd`.

An open choice, flagged deliberately. A hand-written positional inverted index with BM25
scoring is the stronger artifact and the more interesting engineering, but it is days of
work where Postgres FTS is an afternoon. The suggestion is FTS first behind the
`RetrievalStrategy` interface and BM25 later as 8.2, which also makes them directly
comparable through 3.6, a better result than either alone. Tae's call, whenever he gets
to this item.

**3.4 Fusion.**
Reciprocal rank fusion over two or more strategies: `score = sum(1 / (k + rank))` across
lists, `k` from settings, default 60. Fusion works on ranks rather than scores, which is
why the dense and lexical scores never need to be on the same scale.

Tests use hand-constructed rank lists with expected values computed by hand, so the
arithmetic is checked independently of the retrievers.

**3.5 Search CLI.**
`pb search "query" --strategy dense|lexical|hybrid --k N`. Prints rank, score, document
title, heading path, and the first line of the chunk. This is the tool used for the rest
of the area, so readable output is worth the effort.

**3.6 Evaluation harness.**
A YAML file of query-to-expected-chunk pairs, thirty to fifty entries, written by Tae
against the real corpus. `pb eval run --strategy X` computes recall@k, MRR, and
precision@k. `pb eval compare` runs every strategy and prints one table.

The table is the deliverable of this area, not the retriever. It shows that hybrid beats
dense and lexical alone on this corpus, or that it does not. If it does not, that is a
finding to write into `docs/STATUS.md`, not a number to tune until it looks right.

### What done looks like

- `pb search` works for every strategy.
- `pb eval compare` prints recall@5, MRR, and precision@5 per strategy.
- At least thirty queries in the eval set, against the real corpus.
- The result, whatever it is, recorded in the Findings section of `docs/STATUS.md`.

### Worth not doing yet

Cross-encoder reranking. It is a real improvement and it is also the thing most likely to
paper over a weak first-stage retriever, which then never gets fixed. Measure the base
strategies first and it becomes a decision with a number behind it.

---

## Phase 4: Generation

**What this covers.** Retrieval plus a prompt plus an open-weight model, producing an
answer that cites what it used, from the command line.

**Needs first.** 3.1 and at least one working strategy. It does not need 3.6.

### Work in this area

**4.1 Context assembly.**
Takes retrieved chunks and builds the context block: dedupe by document, order by score,
truncate to a token budget from settings, label each chunk with a stable id the model can
cite. Truncation drops whole chunks from the bottom and never splits one.

**4.2 Prompt.**
System prompt as a versioned constant, not an f-string spread through the code. It says:
answer only from the provided context; cite chunk ids; if the context does not contain
the answer, say so and do not fill the gap; the subject is Tae and you are answering on
his portfolio site.

The refusal instruction is the load-bearing one. A portfolio chatbot that invents a job
Tae did not have is worse than one that says it does not know.

**4.3 Model client.**
One `ModelClient` protocol with `complete` and `stream`, and one implementation that
speaks the OpenAI chat-completions shape. That single implementation covers Ollama,
Together, Groq, Fireworks, and DeepInfra, because they all expose that interface. Model
name, base URL, and API key come from settings, so switching providers is configuration.

Timeout, retry with backoff on 429 and 5xx, hard cap on retries. Tests use a fake
implementation of the protocol; no test calls a real endpoint.

Open-weight models are less forgiving than a hosted frontier model about prompt format
and about instruction-following under long context. Expect the refusal behavior from 4.2
to need more explicit phrasing than it would otherwise, and expect to have to strip
preambles some models emit before the answer. Both are worth noting in the code, because
both are things an interviewer can ask about and neither shows up in a framework
tutorial.

**4.3a Local model in development.**
Ollama on the Mac, running `qwen3.5:9b` (about 6.6GB at Q4). No API key, no network, no
per-token cost while iterating on prompts. `make model-up` pulls and serves it.

Point the client at `http://localhost:11434/v1` and it works unchanged. If the same code
path works against Ollama and against a hosted endpoint with only environment variables
different, 4.3 was built correctly.

**4.4 Streaming.**
`stream` yields text deltas as an async generator. Worth building here, in the CLI, where
a failure is a traceback in a terminal. Debugging a streaming bug for the first time
through SSE, a proxy, and a React state update is much harder than debugging it here.

**4.5 Ask pipeline and CLI.**
Joins retrieval, context assembly, and generation. `pb ask "question" --strategy X
--stream` prints the answer and then the citations with their source files.

**4.6 No-context path.**
The explicit case where retrieval returns nothing above a relevance floor. The pipeline
must not call the model with an empty context block; it returns a fixed message. Tested
directly.

### What done looks like

- `pb ask` answers a covered question with citations pointing at real files.
- `pb ask` on something the corpus does not cover says so and cites nothing.
- `pb ask --stream` prints progressively.
- The same code answers against local Ollama and against a hosted endpoint, with only
  environment variables changed.
- No test hits a real model endpoint.

### Worth not doing yet

Conversation history. Multi-turn changes what gets retrieved, because the question "what
about the second one" is meaningless without the previous turn. That makes it a retrieval
problem, not a generation one. Single-turn first.

---

## Phase 5: HTTP API

**What this covers.** Putting phase 4 behind FastAPI and streaming it over the network.

**Needs first.** 4.5. Nothing else.

### Work in this area

**5.1 App and health.**
FastAPI app, lifespan handler opening the connection pool at startup and closing it at
shutdown, embedding model loaded once at startup rather than per request. `GET
/api/health` returning status, git sha, and whether the database answers.

**5.2 Schemas.**
Pydantic models for the chat request (question, optional strategy, optional k) and for
each SSE event type. Input length capped in the schema.

**5.3 Chat endpoint.**
`POST /api/chat`, `text/event-stream`. Events: `sources` once up front with the retrieved
chunks and scores, `delta` per text chunk, `done` with timing, `error`. Sources first
means the UI can show what was retrieved while the answer is still generating.

**5.4 Errors and limits.**
Exception handlers returning a shaped error event, never a stack trace or a connection
string. A per-IP rate limit, because this endpoint costs money per call and the site will
be public. In-memory limiting is fine for one instance; write down that it does not survive
a restart.

**5.5 CORS.**
Allowed origins from settings, localhost in development and the real domain in
production. No wildcard.

**5.6 API tests.**
`httpx.AsyncClient` against the app with a fake generation client. Assert the event
sequence, each event's shape, the rate limit, and malformed input.

### What done looks like

- `make dev` starts the API and `GET /api/health` returns healthy.
- `curl -N -X POST localhost:8000/api/chat -d '{"question":"..."}'` streams `sources`,
  then `delta` events, then `done`.
- The rate limit returns 429 after the configured number of requests.
- API tests pass with no network access.

### Worth not doing yet

Deployment configuration. It is tempting because the API now looks deployable, but every
change made while the frontend is being built means another deploy, and none of them
teach anything.

---

## Phase 6: Frontend

**What this covers.** A site that looks finished, with a chat that streams.

**Needs first.** 5.3 for the chat to talk to. 6.2 and 6.3 need nothing at all and can be
done any time, including before any backend exists.

### Work in this area

**6.1 Next.js scaffold.**
`create-next-app` into `frontend/` with TypeScript, Tailwind, App Router, ESLint. Add
`vitest` and `@testing-library/react`, since `create-next-app` sets up no test runner and
`make test` covers both halves. API base URL from an env var. Add `frontend` to `make
setup`, `dev`, `test`, and `lint`. Delete the generated boilerplate page rather than
building on top of it.

**6.2 Design pass.**
Typography, spacing scale, color, dark mode, written into `tailwind.config.ts` as tokens
before any component exists. This is what stops the site from accumulating six slightly
different button styles. Needs no code and no backend.

**6.3 Layout and static pages.**
Root layout, navigation, footer. About, projects, contact. Content read from the same
markdown as the corpus at build time, so there is one source of Tae's bio and not two
copies that drift.

**6.4 Chat streaming client.**
`fetch` with a `ReadableStream` reader rather than `EventSource`, because the endpoint is
a POST. Parses SSE frames, dispatches by event type, handles mid-stream abort and network
failure. The highest-risk file on the frontend; worth its own tests with a mocked stream.

**6.5 Chat UI.**
Message list, input, a streaming message that grows, loading and error states, a visible
stop button. Autoscroll that stops fighting the user when they scroll up. Enter sends,
shift-enter newlines.

**6.6 Retrieval inspector.**
A collapsible panel per answer showing the retrieved chunks, their scores, their
provenance, and which strategy surfaced them. This is what makes the retrieval work
visible instead of described, and it is nearly free because the `sources` event already
carries everything it needs.

**6.7 Responsive and accessibility.**
Mobile layout, focus states, `aria-live` on the streaming region, keyboard navigation
through the whole site, contrast check.

### What done looks like

- `make dev` starts both services; the site loads and the chat streams end to end.
- The inspector shows real scores.
- The site is usable at phone width and by keyboard alone.
- `make lint` and `make test` pass across both halves.

### Worth not doing yet

Nothing in particular. This is the area where doing things out of order costs least.

---

## Phase 7: Deployment

**What this covers.** A public URL where the chat works against a real database with the
real corpus.

**Needs first.** 6.5 for something worth visiting, and 2.1 for it to have anything to say.

### Work in this area

**7.1 Backend container.**
Multi-stage `Dockerfile`. The embedding model is downloaded into the image at build time,
not at container start, or the first request after every deploy waits on a download.
Non-root user, health check. Confirm it runs locally before deploying it.

**7.2 Managed Postgres.**
Neon project with pgvector enabled, migrations run against it. Confirm the HNSW index
exists there. This is a common thing to get wrong, because a fresh managed database is
not the local one.

**7.3 Backend deploy.**
Fly.io app, secrets through the platform and never in a file, one machine to start.
Confirm `/api/health` over the public URL.

The production model runs on a hosted inference endpoint, not on this machine. Serving a
9B model from the app container needs roughly 8GB of RAM and generates at single-digit
tokens per second on CPU, which costs more per month than the hosted endpoint costs per
year at portfolio traffic. Self-hosting the weights is a legitimate thing to want for its
own sake. If Tae decides the "I served the model myself" story is worth the money, it is
a separate machine with a GPU, not a bigger app container.

**7.4 Frontend deploy.**
Vercel project pointed at `frontend/`, API base URL as an environment variable per
environment. CORS on the backend now names the Vercel domain.

**7.5 Production ingest.**
Run ingestion against the production database. Decide and write down whether this is a
manual command or runs in CI on a push to `content/`. Manual is fine; undecided is not.

**7.6 Domain and TLS.**
Custom domain on Vercel, DNS, certificate. Backend on a subdomain.

**7.7 Observability and cost.**
Structured logs somewhere readable. A spend limit or alert on the model provider account.
A public endpoint calling a paid API with no cap is the one mistake here that costs real
money, and it is not much less true at open-model prices than at frontier prices, because
the failure mode is a loop or a scraper, not normal traffic.

### What done looks like

- The public URL loads and the chat streams an answer with citations.
- The model provider key exists only in platform secret storage.
- A spend cap or alert is configured.
- Deployment steps written down well enough to redo from scratch.

### Worth not doing yet

Autoscaling, CDN tuning, multi-region. One machine serves a portfolio site.

---

## Phase 8: Evaluation and polish

**What this covers.** Numbers to defend the project with, and a repository that reads
well to someone who opens it.

**Needs first.** Varies per item. Everything here is independent of everything else here,
and any of it can be dropped.

### Work in this area

**8.1 Answer quality eval.**
Extends 3.6 past retrieval: a question set with reference answers, scored for
faithfulness and relevance. Record the method next to the numbers, weaknesses included.

**8.2 Hand-written BM25.**
If 3.3 shipped Postgres FTS, implement the positional inverted index and BM25 as a third
strategy and compare all three through `pb eval compare`. The comparison is the artifact,
more than the implementation is.

**8.3 Contextual retrieval.**
Prepend a generated one-sentence document-level context to each chunk before embedding,
per the Anthropic technique. Measure against the current baseline. Keep it only if the
numbers say to.

**8.4 Latency.**
Measure retrieval, first token, and full answer separately. Cache query embeddings. Tune
`ef_search` against measured recall rather than by feel.

**8.5 README and architecture.**
Rewrite `README.md`: what it is, how it works, a diagram, the measured results, the
tradeoffs taken and what would change them, how to run it locally.

**8.6 CI.**
GitHub Actions running lint and tests on push, with real Postgres as a service container.

**8.7 Model comparison.**
Run 8.1 across several open-weight models (a 9B, a 70B, and one more family), changing
nothing but the three model settings. Report faithfulness, refusal rate on
unanswerable questions, and cost per thousand answers.

This is the item that turns "I used an open model" into something defensible. The
interesting result is usually not which model wins; it is finding a question where the
smaller model answers confidently from context that does not support it and the larger one
declines. That is a concrete story about why grounded generation is not solved by
retrieval alone, and it costs one afternoon once 4.3 and 8.1 exist.

### What done looks like

There is no done here. Items get taken when they are worth taking.

---

## Notes on ordering

These are observations, not instructions.

The corpus (2.1) unblocks more than anything else, because the eval set depends on it and
every measurement in phases 3 and 8 depends on the eval set. It is also the only item
Claude Code cannot do.

Phases 0 through 5 produce nothing visual. That is the part of this inventory most likely
to feel wrong around phase 3. The alternative is tuning retrieval by typing questions into
a chat box one at a time, which is why 3.5 and 3.6 exist.

Phase 6 takes longer than it looks. Frontend work is not harder, it is less compressible;
there is no equivalent of a well-specified function signature for "the spacing looks
wrong."

Phase 7 has the sharpest failure mode in the whole inventory, which is 7.7. Everything
else that goes wrong wastes time.
