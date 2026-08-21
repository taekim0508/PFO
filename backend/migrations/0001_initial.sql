-- Initial schema: the corpus, its chunks, and their embeddings.
--
-- Three tables rather than one. A document is a markdown file in content/. A chunk is a
-- slice of one document, small enough for the embedding model to accept. An embedding is
-- the vector for one chunk, kept in its own table so that re-embedding with a different
-- model rewrites vectors without touching text, and so a chunk can exist before it has
-- been embedded.
--
-- No indexes here beyond the ones the constraints create. Those land in 0002.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per source file. content_hash is a fingerprint of the file as ingested, which
-- is what lets re-ingestion skip a file that has not changed.
CREATE TABLE documents (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_path  text        NOT NULL UNIQUE,
    title        text        NOT NULL,
    content_hash text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- One row per slice of a document.
--
-- ordinal is the slice's position within its document, starting at 0, and is unique per
-- document so that reassembling a document in reading order is a plain ORDER BY.
--
-- char_start and char_end are offsets into the source file. They are what lets a citation
-- point at a location in the original markdown rather than at a chunk id.
--
-- heading_path is the trail of markdown headings above the chunk, outermost first, stored
-- as an array so that the innermost heading and "everything under heading X" are both
-- direct queries rather than string splitting.
CREATE TABLE chunks (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  bigint      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ordinal      integer     NOT NULL,
    text         text        NOT NULL,
    token_count  integer     NOT NULL,
    heading_path text[]      NOT NULL DEFAULT '{}',
    char_start   integer     NOT NULL,
    char_end     integer     NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, ordinal)
);

-- One row per embedded chunk. chunk_id is both the primary key and the foreign key, which
-- is what makes the relationship one-to-one.
--
-- The dimension is written literally because it is a property of the schema, not a runtime
-- setting: changing embedding models to one with a different width is a migration, not a
-- configuration change. model_name and model_revision record which model produced the
-- vector, so a mixed-model table is detectable rather than silently wrong.
CREATE TABLE chunk_embeddings (
    chunk_id       bigint PRIMARY KEY REFERENCES chunks (id) ON DELETE CASCADE,
    embedding      vector(384) NOT NULL,
    model_name     text        NOT NULL,
    model_revision text        NOT NULL
);
