"""
NameBio -> Comparable Agent ingest orchestrator.

Reads sales per date from NameBio's table in the shared DB, dedupes by domain
(enrich once per domain, reuse across all its sales), routes each domain by
information content (rule confidence + premium price) into either an
immediately-embedded rule enrichment or a queued LLM upgrade, embeds ONLY
finalized content, and advances a resumable cursor.

CLI:
    python -m src.enrichment.namebio.ingest --backfill --from 2024-01-01 --to 2026-06-16
    python -m src.enrichment.namebio.ingest --daily
"""

import argparse
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import config
from src.enrichment import rule_engine
from src.enrichment.domain_parser import parse_domain
from src.enrichment.namebio import db
from src.enrichment.namebio.embedder import Embedder
from src.enrichment.namebio.enrichment_cache import EnrichmentCache
from src.enrichment.namebio.queue import LLMQueue
from src.enrichment.namebio.routing import decide
from src.enrichment.namebio.sales_source import NamebioSalesSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("namebio.ingest")


class Ingestor:
    def __init__(self, client=None, cache=None, queue=None, embedder=None, conn=None):
        self.conn = conn or db.connect()
        self.client = client or NamebioSalesSource(conn=self.conn)
        self.cache = cache or EnrichmentCache(conn=self.conn)
        self.queue = queue or LLMQueue(conn=self.conn)
        self.embedder = embedder or Embedder(conn=self.conn)

    # ------------------------------------------------------------------ #
    # Per-date ingest
    # ------------------------------------------------------------------ #
    def ingest_date(self, day: date) -> Dict[str, int]:
        """
        Ingest one date. DB failures bubble up so the caller can decide
        whether to skip.
        Returns a stats dict.
        """
        sales = self.client.get_sales_for_date(day)
        stats = defaultdict(int)
        stats["sales"] = len(sales)
        if not sales:
            return dict(stats)

        # Dedupe by domain; keep the best (max) price for premium routing.
        best_price: Dict[str, float] = {}
        sale_meta: Dict[str, Dict] = {}
        for s in sales:
            d = s["domain"]
            p = s.get("price") or 0.0
            if d not in best_price or p > best_price[d]:
                best_price[d] = p
                sale_meta[d] = s  # representative sale (date/platform/price)
        stats["unique_domains"] = len(best_price)

        domains = list(best_price.keys())
        cached = self.cache.get_many(domains)
        stats["cache_hits"] = len(cached)

        rows_to_embed: List[Dict] = []
        pending_records: List[Dict] = []
        pending_queue_items: List = []

        def flush_embeds():
            """Embed accumulated rows and mark them embedded. Called in chunks
            so progress is DURABLE: a crash mid-date keeps already-embedded
            vectors instead of losing the whole date's work."""
            if not rows_to_embed:
                return
            n = self.embedder.embed_and_upsert(rows_to_embed)
            self.cache.mark_embedded_many([r["domain"] for r in rows_to_embed])
            stats["embedded_vectors"] += n
            rows_to_embed.clear()

        def flush_records():
            """Batch-upsert accumulated domain_enrichment records: one round
            trip per chunk instead of one per domain (was the ingest
            bottleneck: ~600ms/statement over a remote pooler)."""
            if not pending_records:
                return
            self.cache.upsert_many(pending_records)
            pending_records.clear()

        def flush_queue():
            if not pending_queue_items:
                return
            self.queue.enqueue_many(pending_queue_items)
            pending_queue_items.clear()

        for d in domains:
            existing = cached.get(d)
            # Cache hit and not stale -> reuse; only (re)embed if missing.
            if existing and not self.cache.is_stale(existing):
                if not existing.get("embedded") and existing.get("status") in (
                    "enriched_rule", "enriched_llm"
                ):
                    rows_to_embed.append(self._embed_row(existing, sale_meta[d]))
                    if len(rows_to_embed) >= config.EMBED_BATCH_SIZE:
                        flush_embeds()
                stats["reused"] += 1
                continue

            # Fresh enrichment via the rule engine.
            enriched = rule_engine.enrich(d)
            decision = decide(enriched["confidence"], best_price[d])

            record = {
                "domain": enriched["domain"],
                "sld": enriched["sld"],
                "tld": enriched["tld"],
                "primary_category": enriched["primary_category"],
                "secondary_category": enriched["secondary_category"],
                "keywords": enriched["keywords"],
                "tokens": enriched["tokens"],
                "descriptions": [enriched["description"]],
                "confidence": enriched["confidence"],
                "source": "rule",
                "status": decision.status,
                "queue_reason": decision.queue_reason,
                "embedded": False,
            }
            pending_records.append(record)
            if len(pending_records) >= config.DB_BATCH_SIZE:
                flush_records()

            stats[decision.status] += 1
            if decision.queue_reason:
                stats[f"queue:{decision.queue_reason}"] += 1

            if decision.enqueue:
                pending_queue_items.append((d, decision.queue_reason))
                if len(pending_queue_items) >= config.DB_BATCH_SIZE:
                    flush_queue()

            if decision.embed_now:
                # carry per-sale fields + enrichment fields for the embed doc
                rows_to_embed.append(self._embed_row(record, sale_meta[d], enriched))
                # Flush in chunks so progress survives an interruption.
                if len(rows_to_embed) >= config.EMBED_BATCH_SIZE:
                    flush_embeds()

        # Final flush for any remainder. Order matters: records must land
        # before we try to embed (embed doesn't depend on it, but keeping the
        # enrichment cache ahead of embeddings avoids a window where a vector
        # exists with no backing domain_enrichment row) and before the
        # embed-triggered mark_embedded_many update.
        flush_records()
        flush_queue()
        flush_embeds()

        logger.info(
            "Date %s | sales=%d unique=%d hits=%d enriched_rule=%d queued=%d embedded=%d",
            day, stats["sales"], stats["unique_domains"], stats["cache_hits"],
            stats.get("enriched_rule", 0), stats.get("queued_for_llm", 0),
            stats.get("embedded_vectors", 0),
        )
        return dict(stats)

    @staticmethod
    def _embed_row(record: Dict, sale: Dict, enriched: Optional[Dict] = None) -> Dict:
        """Merge enrichment + representative-sale fields for the embedder."""
        length = (enriched or {}).get("length")
        has_numbers = (enriched or {}).get("has_numbers")
        # Cache hits have no rule-engine output and domain_enrichment has no
        # length column; without this the vector gets length=null and the
        # search length filter never matches it.
        if length is None or has_numbers is None:
            parsed = parse_domain(record["domain"])
            length = parsed["length"] if length is None else length
            has_numbers = parsed["has_numbers"] if has_numbers is None else has_numbers
        return {
            "domain": record["domain"],
            "tld": record.get("tld"),
            "length": length if length is not None else record.get("length"),
            "primary_category": record.get("primary_category"),
            "secondary_category": record.get("secondary_category"),
            "keywords": record.get("keywords") or [],
            "descriptions": record.get("descriptions") or [],
            "source": record.get("source", "rule"),
            "price": sale.get("price"),
            "date": sale.get("date"),
            "platform": sale.get("platform"),
            "has_numbers": has_numbers if has_numbers is not None else False,
        }

    # ------------------------------------------------------------------ #
    # Cursor / state
    # ------------------------------------------------------------------ #
    def _get_state(self) -> Dict:
        with db.cursor(self.conn) as cur:
            cur.execute("SELECT * FROM ingest_state WHERE id = 1")
            return cur.fetchone() or {}

    def _save_backfill_cursor(self, cursor: date) -> None:
        with db.cursor(self.conn) as cur:
            cur.execute(
                """UPDATE ingest_state
                       SET last_backfill_cursor = %s, updated_at = now()
                     WHERE id = 1""",
                (cursor,),
            )

    def _save_daily_date(self, d: date) -> None:
        with db.cursor(self.conn) as cur:
            cur.execute(
                """UPDATE ingest_state
                       SET last_daily_date = %s, updated_at = now()
                     WHERE id = 1""",
                (d,),
            )

    # ------------------------------------------------------------------ #
    # Drivers
    # ------------------------------------------------------------------ #
    def backfill(self, start: date, end: date) -> None:
        """
        Walk forward from `start` to `end` inclusive, resuming from the saved
        cursor if present. Cursor is saved after each date, so a crash loses at
        most one date and a re-run is idempotent.
        """
        if not self.client.health():
            logger.error("NameBio health check failed; aborting backfill.")
            return

        state = self._get_state()
        resume = state.get("last_backfill_cursor")
        if resume and resume >= start:
            start = resume + timedelta(days=1)
            logger.info("Resuming backfill from %s", start)

        day = start
        while day <= end:
            try:
                self.ingest_date(day)
                self._save_backfill_cursor(day)
            except Exception as e:  # noqa: BLE001 - isolate one bad date
                logger.exception("Date %s failed, skipping: %s", day, e)
            day += timedelta(days=1)

        logger.info("Backfill complete. Cache stats: %s", self.cache.stats())

    def enqueue_tier(self, min_price: float) -> Dict[str, int]:
        """
        Queue every domain with a sale >= min_price that has no vector yet for
        LLM enrichment (nothing is embedded here; the LLM worker embeds after
        it writes the description). The rule-engine result is saved as the
        starting domain_enrichment row (keywords/tokens the worker reuses).
        Domains that already have vectors are skipped, so they are never
        replaced. Idempotent: re-running just re-queues what is still pending.
        """
        sales = self.client.tier_sales(min_price)
        stats = {"domains": len(sales), "premium": 0, "high_value": 0}
        records, items = [], []
        for s in sales:
            enriched = rule_engine.enrich(s["domain"])
            reason = "premium_domain" if s["price"] >= config.PREMIUM_PRICE_THRESHOLD else "high_value"
            stats["premium" if reason == "premium_domain" else "high_value"] += 1
            records.append({
                "domain": enriched["domain"],
                "sld": enriched["sld"],
                "tld": enriched["tld"],
                "primary_category": enriched["primary_category"],
                "secondary_category": enriched["secondary_category"],
                "keywords": enriched["keywords"],
                "tokens": enriched["tokens"],
                "descriptions": [enriched["description"]],
                "confidence": enriched["confidence"],
                "source": "rule",
                "status": "queued_for_llm",
                "queue_reason": reason,
                "embedded": False,
            })
            items.append((s["domain"], reason))
            if len(records) >= config.DB_BATCH_SIZE:
                self.cache.upsert_many(records)
                self.queue.enqueue_many(items)
                records.clear()
                items.clear()
        self.cache.upsert_many(records)
        self.queue.enqueue_many(items)
        logger.info("Tier >= %s queued for LLM: %s", min_price, stats)
        return stats

    def daily(self, day: Optional[date] = None) -> None:
        """Pull a single day (default yesterday), mirroring NameBio's cron."""
        if day is None:
            day = date.today() - timedelta(days=1)
        if not self.client.health():
            logger.error("NameBio health check failed; aborting daily.")
            return
        try:
            self.ingest_date(day)
            self._save_daily_date(day)
        except Exception as e:  # noqa: BLE001
            logger.exception("Daily ingest for %s failed: %s", day, e)

    def close(self):
        self.embedder.close()
        self.conn.close()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv=None):
    parser = argparse.ArgumentParser(description="NameBio ingest pipeline")
    parser.add_argument("--backfill", action="store_true", help="Run a date-range backfill")
    parser.add_argument("--daily", action="store_true", help="Ingest yesterday (cron)")
    parser.add_argument("--enqueue-tier", action="store_true",
                        help="Queue all domains with a sale >= --min-price for LLM enrichment")
    parser.add_argument("--min-price", type=float, default=5000,
                        help="Price floor for --enqueue-tier (default 5000)")
    parser.add_argument("--from", dest="date_from", type=_parse_date)
    parser.add_argument("--to", dest="date_to", type=_parse_date)
    parser.add_argument("--date", dest="single_date", type=_parse_date,
                        help="Ingest one specific date (with --daily)")
    args = parser.parse_args(argv)

    ingestor = Ingestor()
    try:
        if args.backfill:
            if not args.date_from or not args.date_to:
                parser.error("--backfill requires --from and --to")
            ingestor.backfill(args.date_from, args.date_to)
        elif args.daily:
            ingestor.daily(args.single_date)
        elif args.enqueue_tier:
            ingestor.enqueue_tier(args.min_price)
        else:
            parser.error("Specify --backfill, --daily or --enqueue-tier")
    finally:
        ingestor.close()


if __name__ == "__main__":
    main()
