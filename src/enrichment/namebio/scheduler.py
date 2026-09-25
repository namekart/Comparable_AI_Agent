"""
In-process daily NameBio ingest, started with the API.

NameBio's own cron writes the previous day's sales at 08:00 UTC; this embeds
them at DAILY_INGEST_CRON (default 09:00 UTC). Each run also catches up any
days missed while the app was down (up to CATCH_UP_DAYS), and stops at the
first day NameBio has not written yet so that day is retried next run instead
of being marked done with zero sales.

Domains the run queues for LLM enrichment (the ones the rule engine is unsure
about, plus high-value sales) are described and embedded right after the
ingest, with DAILY_LLM_WORKERS parallel workers. Only jobs queued by this run
are touched, so a large older backlog never delays the day's new sales.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from src.enrichment.namebio import db
from src.enrichment.namebio.ingest import Ingestor

logger = logging.getLogger("namebio.scheduler")

# Empty disables the job (e.g. a local API pointed at the production DB).
DAILY_INGEST_CRON = os.getenv("DAILY_INGEST_CRON", "0 9 * * *")
CATCH_UP_DAYS = 7
# Parallel LLM workers for the post-ingest step; 0 disables it.
DAILY_LLM_WORKERS = int(os.getenv("DAILY_LLM_WORKERS", "12"))
# pg advisory lock id, so only one API worker/replica runs the ingest.
_LOCK_KEY = 7310_4452

_scheduler = None


def run_daily_ingest() -> None:
    lock_conn = db.connect()
    try:
        with lock_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s) AS ok", (_LOCK_KEY,))
            if not cur.fetchone()["ok"]:
                logger.info("Daily ingest already running elsewhere; skipping.")
                return
            cur.execute("SELECT last_daily_date FROM ingest_state WHERE id = 1")
            row = cur.fetchone()
        lock_conn.commit()

        run_started = datetime.now(timezone.utc)
        yesterday = run_started.date() - timedelta(days=1)
        last = row["last_daily_date"] if row else None
        start = yesterday - timedelta(days=CATCH_UP_DAYS - 1)
        if last and last + timedelta(days=1) > start:
            start = last + timedelta(days=1)
        if start > yesterday:
            logger.info("Daily ingest up to date (last_daily_date=%s).", last)
            return

        ingestor = Ingestor()
        try:
            day = start
            while day <= yesterday:
                with db.cursor(ingestor.conn) as cur:
                    cur.execute(
                        f"SELECT EXISTS (SELECT 1 FROM {config.NAMEBIO_SALES_TABLE} "
                        f"WHERE sale_date = %s) AS has_sales",
                        (day,),
                    )
                    if not cur.fetchone()["has_sales"]:
                        logger.warning("No NameBio sales for %s yet; will retry next run.", day)
                        break
                ingestor.daily(day)
                # daily() logs and swallows its own errors; only move on once the
                # cursor really advanced, so a failed day isn't skipped over.
                with db.cursor(ingestor.conn) as cur:
                    cur.execute("SELECT last_daily_date FROM ingest_state WHERE id = 1")
                    if cur.fetchone()["last_daily_date"] != day:
                        logger.error("Daily ingest for %s did not complete; will retry next run.", day)
                        break
                day += timedelta(days=1)
        finally:
            ingestor.close()

        if DAILY_LLM_WORKERS > 0 and config.LLM_API_KEY:
            from src.enrichment.namebio.llm_worker import run_workers
            result = run_workers(DAILY_LLM_WORKERS, min_priority=0, updated_after=run_started)
            logger.info("Daily LLM descriptions: %s", result)
    except Exception:  # noqa: BLE001 - never let the job kill the scheduler thread
        logger.exception("Daily ingest run failed")
    finally:
        lock_conn.close()  # also releases the session advisory lock


def start() -> None:
    global _scheduler
    if not DAILY_INGEST_CRON:
        logger.info("DAILY_INGEST_CRON is empty; daily ingest disabled.")
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_daily_ingest,
        CronTrigger.from_crontab(DAILY_INGEST_CRON, timezone="UTC"),
        id="namebio_daily_ingest",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("Daily ingest scheduled: '%s' UTC", DAILY_INGEST_CRON)


def shutdown() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
