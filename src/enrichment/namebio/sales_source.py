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
from typing import Dict, List

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
