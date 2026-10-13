# Index: a conversational portfolio

[![CI](https://github.com/taekim0508/PFO/actions/workflows/ci.yml/badge.svg)](https://github.com/taekim0508/PFO/actions/workflows/ci.yml)

A portfolio site for Tae Kim where the main way in is a conversation. Visitors ask about
his projects and experience, and a chatbot answers from his own written accounts of them,
citing the passages it used. The chatbot speaks as a friend of Tae's, about him in the third
person, and says so when he has not written about something rather than guessing.

The retrieval and generation pipeline is written directly: Postgres with pgvector, hand-
written SQL, no ORM, and no RAG framework. Generation runs on open-weight models behind one
OpenAI-compatible client, so switching models is three settings.

Not yet deployed. Everything below runs locally.

## How a question is answered

```
question
  -> name rewrite        "Tae" becomes "he" before embedding (dense search only)
  -> retrieval           dense: bge-small-en-v1.5 vectors in pgvector (HNSW, cosine)
                         lexical: Postgres full-text search
                         hybrid: both, merged by reciprocal rank fusion
  -> relevance floor     nothing close enough: a fixed "Tae hasn't written about that"
                         reply with his contact details, and the model is never called
  -> context             top passages, numbered [1]..[n], packed into a token budget
  -> prompt              versioned; friend persona; answer only from the passages; cite
  -> model               qwen3.5:9b on Ollama locally, Llama 3.3 70B hosted in production,
                         one client for both, streamed
  -> server-sent events  sources, then the answer as it is written, then done: which
                         passages were cited, and any citation that matches no passage
  -> the site            answer with citation markers, project cards, a sources inspector
```

The corpus is Markdown in `content/`, written by Tae. Ingestion chunks it at headings,
embeds each chunk with its document title and heading path in front, and skips files whose
contents have not changed.

## Measured results

Retrieval is measured, not asserted. `eval/retrieval.yaml` holds 106 questions with the
sections that answer them, including 34 that use Tae's name, each paired with the same
question using "he". Results at k=5, on the real corpus (`pb eval compare`):

| strategy | recall@5 | MRR | precision@5 |
|---|---|---|---|
| dense | 0.818 | 0.722 | 0.262 |
| lexical | 0.621 | 0.522 | 0.181 |
| hybrid | 0.817 | 0.687 | 0.251 |

What the numbers changed:

- **A name in the question was hurting search.** "Tae" appears in no chunk's text, only in
  one document's title, which is embedded with each of that document's chunks. Questions
  naming him were pulled toward that document. Dense MRR was 0.521 on questions with his
  name and 0.758 on the same questions with "he". Six fixes were scored; rewriting the name
  to a pronoun before embedding won, and the paired questions now score identically.
  Rewriting the corpus to name him everywhere also fixed dense search, but broke keyword
  search, which cannot discount a word that appears in every chunk.
- **Hybrid's lead was covering for that bug.** Before the fix hybrid beat dense (MRR 0.674
  against 0.646). After it, dense alone is better at equal recall, so dense is the default.

Answers were checked too: all 106 questions and 15 off-topic ones through the full
pipeline on `qwen3.5:9b`. No answer called Tae "I", no answer cited a passage it was not
given, and all 15 off-topic questions were declined. On a laptop, the first words arrived
in a median of 4.6s.

The full record, with dates, the method, and what was rejected, is in
[`docs/STATUS.md`](docs/STATUS.md) under Findings.

## Decisions worth knowing

- **One store.** Postgres holds documents, chunks, vectors, and the full-text index, so there
  is no second service to run or keep consistent.
- **Sections, not chunks, are the evaluation's answers.** Chunk ids change on every ingest
  and chunk size is one of the things worth measuring, so the eval names sections.
- **No model call without evidence.** Below a similarity floor the pipeline answers with a
  fixed message. The floor sits under every real question rather than between real and
  off-topic ones, because the two overlap and refusing a recruiter's real question is the
  worse mistake; the prompt's own refusal rule catches the rest.
- **Citations are checked.** Every cited number is compared with the passages actually
  given, and a stream that ends without the model saying it finished is an error, never a
  silently cut-off answer.
- **The site quotes the corpus.** Case studies show Tae's write-up sections under fixed
  headings rather than summaries written for the site, and a renamed heading fails the build.

Every decision, with the reason for it, is in the Decisions table in `docs/STATUS.md`.

## Running it locally

You need Docker, [uv](https://docs.astral.sh/uv/), Node 22, and [Ollama](https://ollama.com).

```sh
make setup        # Python and Node dependencies; creates .env from .env.example
                  # then fill in the POSTGRES_* values, DATABASE_URL, and MODEL_API_KEY
make db-up        # Postgres with pgvector in Docker
make migrate      # create the tables and indexes
make ingest       # chunk, embed, and index content/
make model-up     # pull qwen3.5:9b and check it answers
make dev          # API on :8000, site on http://localhost:3000
```

Set `MODEL_REASONING_EFFORT=none` in `.env` for local development: `qwen3.5:9b` otherwise
writes several hundred tokens of hidden reasoning before every answer.

From the command line, without the site:

```sh
cd backend
uv run pb search "Where did Tae go to school?" --strategy hybrid
uv run pb ask "What did Tae build at Abroadly?" --stream
uv run pb eval compare
```

`make test` runs both test suites against a real throwaway Postgres; nothing calls a model
or the network. `make lint` runs ruff, mypy, eslint, prettier, and tsc.

## Layout

```
content/      the corpus: Tae's write-ups, one file per subject
eval/         the retrieval evaluation set
backend/      FastAPI app, the pb CLI, ingestion, retrieval, generation, migrations
frontend/     Next.js site
docs/         ROADMAP.md (the inventory of work), STATUS.md (what exists and why)
```
