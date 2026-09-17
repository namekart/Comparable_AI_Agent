-- =====================================================================
-- 002_stage_data_fixes.sql
-- Repairs NameBio test-ingest rows in domain_embeddings and adds the index
-- the ingest/worker lookups need. Apply manually, like 001. Idempotent.
--
-- Schemas on stage (mxiwrzfxutzchjlrljxg): domain_enrichment,
-- llm_enrichment_queue and ingest_state live in `ai_worker`; the vector
-- corpus the agent searches is `public.domain_embeddings`. The app pins
-- search_path to `ai_worker, public` (config.DB_SEARCH_PATH).
-- =====================================================================

BEGIN;

-- 1) Every NameBio domain was embedded twice (same content). Keep one row per
--    (domain, desc_index), preferring the one that has a length. Removed rows
--    are copied to a backup table first so this is reversible.
CREATE TABLE IF NOT EXISTS ai_worker.domain_embeddings_dupes_backup
    (LIKE public.domain_embeddings INCLUDING DEFAULTS);

WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY metadata->>'domain', metadata->>'desc_index'
               ORDER BY (jsonb_typeof(metadata->'length') = 'number') DESC, id
           ) AS rn
      FROM public.domain_embeddings
     WHERE metadata->>'source' IN ('rule', 'llm')
),
dupes AS (
    SELECT id FROM ranked WHERE rn > 1
),
backed_up AS (
    INSERT INTO ai_worker.domain_embeddings_dupes_backup
    SELECT e.* FROM public.domain_embeddings e JOIN dupes USING (id)
    RETURNING id
)
DELETE FROM public.domain_embeddings e
 USING backed_up b
 WHERE e.id = b.id;

-- 2) Ingest's cache-hit path wrote length = null (and has_numbers = false), so
--    the search length filter never matched these rows. length = SLD length,
--    the same value tldextract gives for the corpus rows.
UPDATE public.domain_embeddings
   SET metadata = metadata
       || jsonb_build_object(
            'length', char_length(metadata->>'domain') - char_length(metadata->>'tld'),
            'has_numbers', left(metadata->>'domain',
                                char_length(metadata->>'domain') - char_length(metadata->>'tld')) ~ '[0-9]'
          )
 WHERE metadata->>'source' IN ('rule', 'llm')
   AND jsonb_typeof(metadata->'length') IS DISTINCT FROM 'number'
   AND right(lower(metadata->>'domain'), char_length(metadata->>'tld')) = lower(metadata->>'tld');

COMMIT;

-- 3) Embedder deletes and llm_worker looks up vectors by metadata->>'domain';
--    without this both scan the whole table (grows to ~883k rows on backfill).
CREATE INDEX IF NOT EXISTS idx_domain_embeddings_meta_domain
    ON public.domain_embeddings ((metadata->>'domain'));
