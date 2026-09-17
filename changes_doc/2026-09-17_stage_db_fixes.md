# 2026-09-17 — Stage DB table resolution and NameBio search fixes

## Summary

The Comparable Agent was reading and writing different vector tables, so
NameBio sales imported by the ingest pipeline never showed up in search. Some
imported rows were also duplicated or missing `length`, which hid them from the
search filters, and the recency score was stuck at a constant because of a typo.

After these changes:

- Search and ingest use one table setting, `DOMAIN_EMBEDDINGS_TABLE`
  (`domain_embeddings`).
- Every DB connection pins `search_path`, so table names resolve the same way
  everywhere.
- The search client reconnects if the pooler drops its connection.
- Recency scoring works.
- Existing NameBio rows on stage are de-duplicated and have `length` filled in.

## Database this app uses

| Supabase project | Region | Role |
|---|---|---|
| `mxiwrzfxutzchjlrljxg` | `aws-1-us-west-1` | name.ai **stage**, the Comparable Agent's DB |

Schemas on stage:

| Schema | Tables |
|---|---|
| `public` | `domain_embeddings`: the vector corpus search reads (12,525 rows at startup on 2026-09-17) |
| `ai_worker` | `domain_enrichment`, `llm_enrichment_queue`, `ingest_state`, `domain_embeddings_dupes_backup` |
| `domainvaluation1` | `domain_embeddings`: a different shape (no `content`/`id`), **not usable by this app** |

The name.ai production DB (the Coolify `DATABASE_URL` in the name.ai app) is a
separate Supabase project. This app does not use it. The app also does not read
`DATABASE_URL` / `DIRECT_URL`; it only reads `SUPABASE_*`.

## Code changes

### `src/enrichment/retrieval/supabase_client.py`
- Connects through `namebio.db.connect()`, so it gets the same `search_path`
  and `RealDictCursor` as the ingest pipeline.
- Runs in autocommit. The connection lives for the whole API process, and a
  single failed read must not leave it in an aborted transaction.
- New `_execute()` reconnects once on `OperationalError` / `InterfaceError`
  (for example, when the pooler drops an idle connection).
- The search query and `count()` read from `config.DOMAIN_EMBEDDINGS_TABLE`
  instead of a hardcoded `domain_embeddings`.

### `src/enrichment/namebio/db.py`
- `connect()` runs `set_config('search_path', DB_SEARCH_PATH, false)` and
  commits it, so a later rollback cannot undo it.
- **Requires the 5432 session pooler.** The 6543 transaction pooler does not
  keep session settings.

### `config.py`
- New `DB_SEARCH_PATH` (default `ai_worker, public`).
- `DOMAIN_EMBEDDINGS_TABLE` default changed from
  `domainvaluation1.domain_embeddings` to `domain_embeddings`.

### `src/enrichment/retrieval/scoring.py`: bug fix
- `compute_recency_weight(sale_data)` used `sale_date` in its body. The
  `NameError` was swallowed by `except Exception: return 0.5`, so **every
  candidate got recency 0.5**. The parameter is now `sale_date`, and recency
  follows `RECENCY_BANDS` (1.0 down to 0.3) as intended.

### `src/enrichment/namebio/ingest.py`: bug fix
- On an enrichment-cache hit there is no rule-engine output, and
  `domain_enrichment` has no `length` column. Vectors were written with
  `length = null`, so the search length filter never matched them.
  `length` / `has_numbers` are now filled from `parse_domain()` when missing.

### `sql/002_stage_data_fixes.sql` (new)
One-off repair for rows the old ingest wrote. Apply manually, like `001`. It is
idempotent. The README records it as applied on stage on 2026-09-17.
1. Every NameBio domain had been embedded twice. It keeps one row per
   `(domain, desc_index)`, preferring the row that has a `length`, and first
   copies the removed rows to `ai_worker.domain_embeddings_dupes_backup`.
2. Fills `length` and `has_numbers` on NameBio rows where they are missing.
3. Adds index `idx_domain_embeddings_meta_domain` on `metadata->>'domain'`.
   The embedder's delete and the LLM worker's lookup would otherwise scan the
   whole table.

### Docs and comments
- `README_NAMEBIO.md`: stage schema layout, the `DB_SEARCH_PATH` row, and the
  new `DOMAIN_EMBEDDINGS_TABLE` default.
- `src/enrichment/namebio/embedder.py` docstring and the
  `sql/001_namebio_integration.sql` header now name the configured table.

## Environment changes (not in git)

| Where | Change |
|---|---|
| `Comparable_AI_Agent/.env` | `DOMAIN_EMBEDDINGS_TABLE=domain_embeddings` (was `domainvaluation1.domain_embeddings`). `.env.example`, which held real secrets and was not gitignored, was renamed to `.env`. |
| `nameaiv1/.env` (commented stage `DATABASE_URL`) | Host `aws-0-us-west-1.pooler.supabase.com` → `aws-1-us-west-1.pooler.supabase.com`. The `aws-0` host returns `tenant/user not found`; the fixed URL connects. The `db-fix-stage` scripts still work. |

**Before deploying, check the Coolify env for this app:**
- `DOMAIN_EMBEDDINGS_TABLE` must be `domain_embeddings` (or unset). If it is
  still `domainvaluation1.domain_embeddings`, search will now read that table
  and break.
- `SUPABASE_PORT` must be `5432`.
- `DB_SEARCH_PATH` can stay unset (the default is `ai_worker, public`).

## Verification (local, 2026-09-17)

Ran `uvicorn api:app` from `.venv` (Python 3.11) against stage:

| Check | Result |
|---|---|
| Startup and DB connection | OK: 12,525 rows in `domain_embeddings` |
| `GET /health` | `healthy`, `agent_loaded: true` |
| Retrieval and scoring for `onepay.ai` | 10 comparables found and scored, with real recency values (0.80) |
| LLM enrichment (OpenRouter) | **Failed: 402**, account out of credits |
| `POST /api/v1/search` response | `success: false`, because of the LLM failure above |

## Open issues / follow-ups

1. **OpenRouter account balance is empty** (about −$0.20). Every search returns
   `success: false` until credits are added.
2. **No `max_tokens` on the LLM call** (`llm_enricher.py`). OpenRouter reserves
   the model maximum (65,536 tokens) per request, so each call needs far more
   balance than it uses. A cap of about 2,000 is enough for the JSON response.
3. **An LLM failure fails the whole search.** `enrichment_node` falls back to
   placeholder descriptions, but `api.py` treats any `error` in state as
   failure and returns no data.
4. **Rotate credentials.** The stage DB password and the OpenRouter key were
   shared in plain text while debugging.
