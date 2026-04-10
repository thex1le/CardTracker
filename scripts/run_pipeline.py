"""Run the full CardEdge daily pipeline.

Usage: python scripts/run_pipeline.py [--skip-ingest] [--skip-scores] [--skip-alerts]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")


async def main(skip_ingest: bool, skip_scores: bool, skip_alerts: bool) -> None:
    start = time.time()

    if not skip_ingest:
        logger.info("=== Step 1/3: Daily Ingest ===")
        from app.jobs.run_daily_ingest import run_daily_ingest
        await run_daily_ingest()
    else:
        logger.info("Skipping ingest")

    if not skip_scores:
        logger.info("=== Step 2/3: Score Refresh ===")
        from app.jobs.run_score_refresh import run_score_refresh
        await run_score_refresh()
    else:
        logger.info("Skipping scores")

    if not skip_alerts:
        logger.info("=== Step 3/3: Alert Generation ===")
        from app.jobs.run_alerts import run_alerts
        await run_alerts()
    else:
        logger.info("Skipping alerts")

    elapsed = time.time() - start
    logger.info("Pipeline complete in %.1f seconds", elapsed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full CardEdge daily pipeline")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip data ingestion")
    parser.add_argument("--skip-scores", action="store_true", help="Skip score computation")
    parser.add_argument("--skip-alerts", action="store_true", help="Skip alert generation")
    args = parser.parse_args()
    asyncio.run(main(args.skip_ingest, args.skip_scores, args.skip_alerts))
