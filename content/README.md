# content

The corpus the chatbot answers from. `make ingest` mirrors this directory into the
database: new and edited files are chunked and embedded, unchanged files are skipped, and
a deleted file's chunks are removed. This README is not ingested.

Everything here is first-person writing by Tae. The bot can only say what these files
say, so a sentence here is a claim the bot will repeat to a recruiter. Keep each fact in
one file; the same story in two places makes both copies compete for the same retrieval
slots.

## Shape of a file

```markdown
---
title: AI Producer Internship, Ambassador Matching Pipeline
---

## The problem: matching students with AI ambassadors

Prose about one thing...

## Why the system decides matches instead of recommending options

Prose about the next thing...
```

- **Front matter is required** and must include `title`. Every chunk is labelled with it,
  both for retrieval and for citations, so make it name the subject on its own. A file
  without a title is reported as failed and skipped.
- **One file per subject**: one project, one job, education, and so on.
- **Headings carry meaning.** Chunks never cross a heading, and each chunk is embedded
  with its document title and the headings above it. A heading that reads as an answer
  to a likely question ("Why magic links instead of passwords") retrieves better than one
  that does not ("Auth").
- **Sections of a few paragraphs work best.** A section longer than `CHUNK_SIZE`
  characters (1000 by default) is split at blank lines, then at sentence ends.

## After editing

Run `make ingest`. Only the files that changed are re-processed. After changing
`CHUNK_SIZE` or `CHUNK_OVERLAP`, run `cd backend && uv run pb ingest --force`, because
those settings are not part of a file's fingerprint.
