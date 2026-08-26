-- Indexes for the two retrieval arms.
--
-- Separate from 0001 on purpose. Indexes are the part of the schema most likely to change
-- once there is real data to measure, and keeping them in their own file makes that a
-- normal new migration rather than an edit to committed history.
--
-- Both are created with a plain CREATE INDEX rather than CREATE INDEX CONCURRENTLY.
-- Concurrently does not block writes to the table while it builds, but it cannot run
-- inside a transaction, and the runner deliberately wraps every migration in one. At this
-- corpus size the build is well under a second and the lock is not observable. This is the
-- trade to revisit the first time an index is added to a live table carrying traffic.
--
-- No standalone btree on chunks.document_id, which is the third index this file might have
-- been expected to contain. The UNIQUE (document_id, ordinal) constraint in 0001 already
-- created a btree whose leading column is document_id, and Postgres uses a composite index
-- for a lookup on a leading-column prefix. A second index would locate exactly the same
-- rows while adding write cost to every chunk ingestion.

-- The vector arm. A question is embedded into the same 384-dimension space as the corpus,
-- and the chunks worth reading are the ones whose vectors sit closest to it. Without an
-- index that is a distance computation against every row. HNSW instead builds a layered
-- graph linking each vector to a few of its nearest neighbors, so a search walks toward the
-- answer through a few hundred nodes instead of scanning the table. It is approximate: the
-- walk can settle short of the true nearest neighbor, which is the price of the speed.
--
-- vector_cosine_ops is what binds this index to the <=> operator. Built with a different
-- operator class the index would still exist and every cosine query would silently ignore
-- it, which is why the test asserts on the query plan and not on pg_indexes alone.
--
-- m and ef_construction are written out rather than defaulted. Both values are pgvector's
-- own defaults, so this changes nothing today. The point is that a later tuning pass is an
-- edit to a visible number instead of the discovery that a default was in play all along.
-- m is how many links each node keeps, ef_construction how wide the search is while
-- building. Both trade build time and memory for recall.
CREATE INDEX chunk_embeddings_embedding_hnsw
    ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- The lexical arm. Vector search finds chunks that mean something similar to the question;
-- this finds chunks that contain the words the question actually used. The two fail in
-- different directions, which is the reason phase 3 runs both and fuses the results.
--
-- GIN is an inverted index: rather than one entry per row, it stores one entry per lexeme
-- pointing at every chunk containing it. to_tsvector does the work of producing those
-- lexemes, lowercasing, dropping stop words, and stemming, so "indexing" and "indexes" land
-- under the same key.
--
-- This is an expression index, so the planner only uses it for a query that spells the
-- expression identically. The lexical arm in phase 3 has to write to_tsvector('english',
-- text) and not a variation that merely means the same thing. The language is named
-- explicitly for a second reason: the one-argument to_tsvector reads a session setting,
-- which makes it non-immutable and therefore not indexable at all.
CREATE INDEX chunks_text_fts
    ON chunks
    USING gin (to_tsvector('english', text));
