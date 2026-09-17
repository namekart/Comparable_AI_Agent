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
- LLM enrichment uses free OpenRouter models, with automatic fallback models
  and retries, because the OpenRouter account balance is empty.

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
- The setting only sticks on the 5432 session pooler. The 6543 transaction
  pooler does not keep session settings; there the stage `postgres` role's own
  default (`ai_worker, public`) applies, which is the same value.

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

### `config.py` + `src/enrichment/llm_enricher.py`: free LLM models
The OpenRouter account balance is empty, so the paid model (`openai/gpt-5.1`)
returned 402 on every call. Free (`:free`) models still work. The key allows
1,000 free-model requests per day, and one search normally uses one request.
- `LLM_MODEL` is now read from the environment. The default is
  `nvidia/nemotron-3-super-120b-a12b:free`.
- New `LLM_FALLBACK_MODELS` (default `z-ai/glm-5.2:free,google/gemma-4-31b-it:free`).
  These are sent as OpenRouter's `models` list, so OpenRouter tries the next
  model when one is overloaded or rate-limited.
- New `LLM_MAX_ATTEMPTS` (default 3). `enrich_domain()` retries the call.
  Free providers sometimes return HTTP 200 with an error body and no
  `choices`; `langchain-openai` 0.0.8 raises `TypeError` on that. Before this
  change, about 1 in 3 calls failed that way.
- The paid path still works: set `LLM_MODEL` (for example
  `mistralai/mistral-nemo`, the cheapest paid model) once credits are added.
- Free providers may log prompts. Only the domain name is sent.

### Scoring: meaning first (`scoring.py`, `supabase_client.py`, `config.py`)
- `semantic_sim` is now **cosine similarity**. The search SQL returns
  `1 - (embedding <=> query)` and orders by `<=>`. Candidate order is unchanged,
  because all vectors are unit length. The old `1 / (1 + L2)` put every
  candidate at roughly 0.42–0.47. Meaning then moved a score by ~0.005, while
  one recency step moved it by 0.04, so the best-fitting sales lost.
- Recency is **interpolated** between the old band levels (`RECENCY_CURVE`),
  replacing `RECENCY_BANDS`. A sale 371 days old used to drop from 0.8 to 0.6
  overnight; now it gets 0.797.
- `MIN_SEMANTIC_SIM` (`weak_match`) keeps 0.5: for unit vectors 1/(1+L2) = 0.5
  exactly when cosine = 0.5. Weights, `MIN_SCORE_THRESHOLD`, top-K and response
  fields are unchanged.

Old vs new on the same retrieved candidates (stage, 11 live enrichments):

| Domain | Count old → new | Same domains | Avg cosine old → new | Weak old → new |
|---|---|---|---|---|
| 42go.com | 10 → 10 | 1 | 0.521 → 0.584 | 1 → 0 |
| centurio.ai | 10 → 10 | 6 | 0.583 → 0.631 | 2 → 0 |
| cloudkitchen.io | 10 → 10 | 9 | 0.371 → 0.377 | 9 → 9 |
| genomics.io | 9 → 9 | 9 | 0.235 → 0.235 | 9 → 9 |
| isotope.co | 10 → 10 | 7 | 0.340 → 0.365 | 10 → 10 |
| lawfirm.com | 10 → 10 | 8 | 0.500 → 0.553 | 5 → 3 |
| mortgagebroker.com | 10 → 10 | 7 | 0.500 → 0.523 | 4 → 2 |
| onepay.ai | 10 → 10 | 4 | 0.591 → 0.644 | 0 → 0 |
| petfood.shop | 10 → 10 | 7 | 0.404 → 0.419 | 10 → 10 |
| pharmaco.com | 10 → 10 | 6 | 0.547 → 0.578 | 2 → 1 |
| zenith.ai | 10 → 10 | 5 | 0.629 → 0.655 | 0 → 0 |

For example, `onepay.ai` now leads with paid.ai, payper.ai, trustpay.ai and
zhifu.ai (cosine 0.64–0.72) instead of insura/term/told/automed. Domains that
stay weak (`isotope.co`, `genomics.io`, `petfood.shop`) have no close sales in
the corpus. Scoring cannot fix that; more ingested sales can.

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
- `SUPABASE_PORT` must be `6543` on Hetzner. Hetzner blocks outbound TCP 5432
  to the Supabase poolers (both host and containers time out), so on 5432 the
  app crash-loops at startup and the site returns 502. Login over 6543 works.
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

After switching to free models with fallback and retry:

| Domain | Result | Time | Categories |
|---|---|---|---|
| `onepay.ai` | `success: true`, 10 comparables | 18 s | Descriptive / Service-based |
| `cloudchef.com` | `success: true`, 10 comparables | 19 s | Combination / Service-based |
| `zenly.io` | `success: true`, 10 comparables | 27 s | Brandable / Combination |
| `isotope.co` | `success: true`, 10 comparables | 25 s | Descriptive / Brandable |

The cost was $0 for all four. Categories for the same domain can differ
between runs, because the LLM output is not deterministic.

## Open issues / follow-ups

1. **OpenRouter account balance is empty** (about −$0.20). Searches run on free
   models for now (see above). They are rate-limited and can be slow, 18–27 s
   per search.
2. **No `max_tokens` on the LLM call** (`llm_enricher.py`). This only matters
   for paid models. OpenRouter reserves the model maximum (65,536 tokens) per
   request, so each call needs far more balance than it uses. A cap of about
   2,000 is enough for the JSON response.
3. **An LLM failure fails the whole search.** `enrichment_node` falls back to
   placeholder descriptions, but `api.py` treats any `error` in state as
   failure and returns no data.
4. **Rotate credentials.** The stage DB password and the OpenRouter key were
   shared in plain text while debugging.
5. **Weak comparables still fill all 10 slots.** (Similarity compression and
   recency cliffs fixed in "Scoring: meaning first"; the threshold, price
   outliers and thin corpus remain.) For `isotope.co`, the #1 match
   was `sigma.io` ($100,000) at cosine similarity 0.35. The only link was
   "SaaS platform + data analytics" in both descriptions. Causes:
   - `MIN_SCORE_THRESHOLD = 0.4` filters almost nothing, because category plus
     recency alone can reach 0.30–0.40.
   - `1 / (1 + distance)` compresses similarity into roughly 0.45–0.55.
   - Price outliers are not flagged.
6. **Corpus freshness.** The newest sales returned were from Nov 2025. Check that
   the daily NameBio ingest is running.
7. **Junk sales in the corpus.** For example, `cloudsty.com` sold for $1.
