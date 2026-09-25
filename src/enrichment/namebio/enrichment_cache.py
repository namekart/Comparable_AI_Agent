"""
CRUD for the permanent, versioned domain_enrichment cache.

This is what makes every expensive computation a one-time cost: once a domain
is enriched (by rule or LLM) the result is cached forever and reused across
all of that domain's sales and all future runs. Versioning lets a future
tokenizer/model improvement selectively refresh stale rows via
`WHERE enrichment_version < CURRENT` instead of a full rebuild.
"""

import json
import logging
from typing import Dict, List, Optional

from psycopg2.extras import execute_values

import config
from src.enrichment.namebio import db

logger = logging.getLogger(__name__)

_COLUMNS = [
    "domain", "sld", "tld", "primary_category", "secondary_category",
    "keywords", "tokens", "descriptions", "confidence", "source",
    "status", "queue_reason", "embedded", "enrichment_version",
    "embedding_version",
]


class EnrichmentCache:
    def __init__(self, conn=None):
        self._own_conn = conn is None
        self.conn = conn or db.connect()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, domain: str) -> Optional[Dict]:
        domain = domain.lower()
        with db.cursor(self.conn) as cur:
            cur.execute(
                "SELECT * FROM domain_enrichment WHERE domain = %s", (domain,)
            )
            return cur.fetchone()

    def get_many(self, domains: List[str]) -> Dict[str, Dict]:
        """Return {domain: row} for the domains that exist in cache."""
        if not domains:
            return {}
        domains = [d.lower() for d in domains]
        with db.cursor(self.conn) as cur:
            cur.execute(
                "SELECT * FROM domain_enrichment WHERE domain = ANY(%s)",
                (domains,),
            )
            return {row["domain"]: row for row in cur.fetchall()}

    def is_stale(self, row: Dict) -> bool:
        """True if the cached row predates the current enrichment version."""
        return (row or {}).get("enrichment_version", 0) < config.CURRENT_ENRICHMENT_VERSION

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def upsert(self, record: Dict) -> None:
        """
        Insert or update a domain_enrichment row. `record` keys mirror the
        table columns; jsonb fields (keywords/tokens/descriptions) accept
        python lists. Always bumps updated_at.
        """
        record = dict(record)
        record["domain"] = record["domain"].lower()
        record.setdefault("enrichment_version", config.CURRENT_ENRICHMENT_VERSION)
        record.setdefault("embedding_version", config.CURRENT_EMBEDDING_VERSION)

        cols = [c for c in _COLUMNS if c in record]
        json_cols = {"keywords", "tokens", "descriptions"}
        placeholders = []
        values = []
        for c in cols:
            if c in json_cols:
                placeholders.append("%s::jsonb")
                values.append(json.dumps(record[c]))
            else:
                placeholders.append("%s")
                values.append(record[c])

        update_cols = [c for c in cols if c != "domain"]
        set_clause = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in update_cols
        ) + ", updated_at = now()"

        sql = f"""
            INSERT INTO domain_enrichment ({", ".join(cols)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT (domain) DO UPDATE SET {set_clause};
        """
        with db.cursor(self.conn) as cur:
            cur.execute(sql, values)

    def upsert_many(self, records: List[Dict]) -> None:
        """
        Batched version of upsert(): one round trip for the whole list instead
        of one per record. This is the difference between ~2,500 network round
        trips (~600ms each over a remote pooler) and one per ingest date.
        """
        if not records:
            return

        json_cols = {"keywords", "tokens", "descriptions"}
        rows = []
        for record in records:
            record = dict(record)
            record["domain"] = record["domain"].lower()
            record.setdefault("enrichment_version", config.CURRENT_ENRICHMENT_VERSION)
            record.setdefault("embedding_version", config.CURRENT_EMBEDDING_VERSION)
            row = []
            for c in _COLUMNS:
                v = record.get(c)
                if c in json_cols:
                    v = json.dumps(v if v is not None else [])
                row.append(v)
            rows.append(tuple(row))

        update_cols = [c for c in _COLUMNS if c != "domain"]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols) + ", updated_at = now()"
        template = "(" + ", ".join(
            "%s::jsonb" if c in json_cols else "%s" for c in _COLUMNS
        ) + ")"
        sql = f"""
            INSERT INTO domain_enrichment ({", ".join(_COLUMNS)})
            VALUES %s
            ON CONFLICT (domain) DO UPDATE SET {set_clause};
        """
        with db.cursor(self.conn) as cur:
            execute_values(cur, sql, rows, template=template, page_size=len(rows))

    def mark_embedded(self, domain: str, embedding_version: int = None) -> None:
        self.mark_embedded_many([domain], embedding_version)

    def mark_embedded_many(self, domains: List[str], embedding_version: int = None) -> None:
        if not domains:
            return
        ev = embedding_version or config.CURRENT_EMBEDDING_VERSION
        domains = [d.lower() for d in domains]
        with db.cursor(self.conn) as cur:
            cur.execute(
                """UPDATE domain_enrichment
                       SET embedded = true, embedding_version = %s, updated_at = now()
                     WHERE domain = ANY(%s)""",
                (ev, domains),
            )

    def set_status(self, domain: str, status: str, queue_reason: str = None) -> None:
        with db.cursor(self.conn) as cur:
            cur.execute(
                """UPDATE domain_enrichment
                       SET status = %s, queue_reason = %s, updated_at = now()
                     WHERE domain = %s""",
                (status, queue_reason, domain.lower()),
            )

    def stats(self) -> Dict[str, int]:
        """Counts by status (for logging/observability)."""
        with db.cursor(self.conn) as cur:
            cur.execute(
                "SELECT status, count(*) AS n FROM domain_enrichment GROUP BY status"
            )
            return {row["status"]: row["n"] for row in cur.fetchall()}

    def close(self):
        if self._own_conn and self.conn:
            self.conn.close()
