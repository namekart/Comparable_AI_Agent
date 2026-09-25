"""
NameBio sales, read straight from the NameBio service's own table in the
shared Hetzner Postgres (config.NAMEBIO_SALES_TABLE). NameBio's daily cron
writes the previous day's sales there around 08:00; this reads them back in
the shape the ingest pipeline expects:

    namebio_sale column  -> agent field
    ------------------------------------
    domain               -> domain   (lowercased)
    price                -> price
    sale_date            -> date     (ISO yyyy-mm-dd)
    marketplace          -> platform
"""

import logging
from datetime import date
from typing import Dict, List, Optional

import config
from src.enrichment.namebio import db

logger = logging.getLogger(__name__)


class NamebioSalesSource:
    def __init__(self, conn):
        self.conn = conn
        self.table = config.NAMEBIO_SALES_TABLE

    def health(self) -> bool:
        try:
            with db.cursor(self.conn) as cur:
                cur.execute(f"SELECT 1 FROM {self.table} LIMIT 1")
            return True
        except Exception as e:  # noqa: BLE001 - health check must not throw
            logger.warning("NameBio sales table %s unreachable: %s", self.table, e)
            return False

    def get_sales_for_date(self, day: date) -> List[Dict]:
        with db.cursor(self.conn) as cur:
            cur.execute(
                f"""SELECT domain, price, sale_date, marketplace
                      FROM {self.table}
                     WHERE sale_date = %s""",
                (day,),
            )
            rows = cur.fetchall()

        sales = [
            {
                "domain": r["domain"].strip().lower(),
                "price": float(r["price"]) if r["price"] is not None else 0.0,
                "date": r["sale_date"].isoformat(),
                "platform": r["marketplace"],
            }
            for r in rows
            if r["domain"]
        ]
        logger.info("NameBio %s: read %d sales from %s", day, len(sales), self.table)
        return sales

    def tier_sales(self, min_price: float) -> List[Dict]:
        """
        One representative sale (the highest-priced) per domain with a sale at
        or above `min_price`, skipping domains that already have a vector so
        their existing embeddings are never replaced.
        """
        with db.cursor(self.conn) as cur:
            cur.execute(
                f"""SELECT DISTINCT ON (lower(s.domain))
                           lower(s.domain) AS domain, s.price, s.sale_date, s.marketplace
                      FROM {self.table} s
                     WHERE s.price >= %s
                       AND NOT EXISTS (
                           SELECT 1 FROM {config.DOMAIN_EMBEDDINGS_TABLE} e
                            WHERE e.metadata->>'domain' = lower(s.domain))
                     ORDER BY lower(s.domain), s.price DESC, s.sale_date DESC""",
                (min_price,),
            )
            rows = cur.fetchall()
        sales = [
            {
                "domain": r["domain"].strip(),
                "price": float(r["price"]),
                "date": r["sale_date"].isoformat(),
                "platform": r["marketplace"],
            }
            for r in rows
            if r["domain"]
        ]
        return sorted(sales, key=lambda s: -s["price"])

    def best_sale_for_domain(self, domain: str) -> Optional[Dict]:
        with db.cursor(self.conn) as cur:
            cur.execute(
                f"""SELECT price, sale_date, marketplace FROM {self.table}
                     WHERE lower(domain) = lower(%s)
                     ORDER BY price DESC NULLS LAST, sale_date DESC LIMIT 1""",
                (domain,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "price": float(r["price"]) if r["price"] is not None else None,
            "date": r["sale_date"].isoformat(),
            "platform": r["marketplace"],
        }
