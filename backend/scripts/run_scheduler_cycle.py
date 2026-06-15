"""Run one full scheduler cycle (all queries, all sources, persist to DB).

Usage:
    uv run python scripts/run_scheduler_cycle.py

Each query runs in its own subprocess. If the browser crashes (EPIPE etc.),
the subprocess dies and the parent immediately starts the next query in a fresh
subprocess. Checkpoints are saved in the DB so a restart resumes from the last
completed query.

SCHEDULER_ENABLED=false is NOT required — this script runs standalone.
"""

from __future__ import annotations

import asyncio
import random
import subprocess
import sys
import os
from datetime import UTC, datetime
from pathlib import Path

# Add src to path so we can import jobs_finder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobs_finder.infrastructure.config import Settings

# ── Checkpoint helpers ────────────────────────────────────────────────────────

_CHECKPOINT_GET_SQL = "SELECT value FROM scheduler_checkpoint WHERE key = 'last_completed_query'"
_CHECKPOINT_SET_SQL = (
    "INSERT INTO scheduler_checkpoint (key, value) VALUES ('last_completed_query', ?)"
    " ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)
_CREATE_CHECKPOINT_SQL = """
CREATE TABLE IF NOT EXISTS scheduler_checkpoint (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
)
"""


def _get_checkpoint(db_path: str) -> int:
    """Return 0-indexed last completed query, or -1 if none."""
    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(_CREATE_CHECKPOINT_SQL)
    try:
        row = con.execute(_CHECKPOINT_GET_SQL).fetchone()
        val = int(row[0]) if row else -1
    except Exception:
        val = -1
    con.close()
    return val


def _set_checkpoint(db_path: str, query_index: int) -> None:
    """Save completed query index (0-based)."""
    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(_CREATE_CHECKPOINT_SQL)
    con.execute(_CHECKPOINT_SET_SQL, (str(query_index),))
    con.commit()
    con.close()


# ── Subprocess per-query runner ───────────────────────────────────────────────

async def run_single_query(
    query_index: int,
    total_queries: int,
    keywords: str,
    location: str,
    db_path: str,
) -> tuple[int, int, int, int, int, str]:  # qi, total, unique, new, errors, failed_sources
    """Run one query in a fresh subprocess. Returns (qi, total, unique, new, errors, failed_sources)."""
    script = Path(__file__).resolve()
    cmd = [
        sys.executable,
        str(script),
        "--query-only",
        "--qi", str(query_index),
        "--total", str(total_queries),
        "--keywords", keywords,
        "--location", location,
        "--db", db_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min per query
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0 and stdout:
            parts = stdout.split(",")
            if len(parts) == 4:
                unique = int(parts[0])
                new = int(parts[1])
                errors = int(parts[2])
                failed = parts[3]
                return query_index, total_queries, unique, new, errors, failed

        # Nonzero rc or parse error
        err_summary = f"rc={result.returncode}" if result.returncode != 0 else "parse_error"
        return query_index, total_queries, 0, 0, 1, f"{err_summary}: {stderr[:300]}"
    except subprocess.TimeoutExpired:
        return query_index, total_queries, 0, 0, 1, "query timed out after 300s"
    except Exception as exc:
        return query_index, total_queries, 0, 0, 1, str(exc)

    return query_index, total_queries, 0, 0, 1, "unknown error"


# ── Main cycle ───────────────────────────────────────────────────────────────

async def run_cycle() -> None:
    settings = Settings()
    queries = settings.scheduler_queries
    db_path = settings.db_path or "jobs.db"

    # Load checkpoint
    last_completed = _get_checkpoint(db_path)
    start_index = last_completed + 1  # resume after last completed

    print(f"[*] Scheduler one-shot run")
    print(f"[*] DB: {db_path}")
    print(f"[*] Queries: {len(queries)}")
    print(f"[*] Sources: linkedin, indeed, infojobs")
    print(f"[*] Checkpoint: last completed query = {last_completed} ({last_completed + 1}/{len(queries)})")
    if start_index > 0:
        print(f"[*] Resuming from query {start_index + 1}/{len(queries)}...")
    print()

    total_new = 0
    total_seen = 0
    total_errors = 0

    for qi, query in enumerate(queries):
        if qi < start_index:
            print(f"[{qi+1:2d}/{len(queries)}] {query['keywords']:30s} @ {query['location']}... SKIP (done)")
            continue

        keywords = query["keywords"]
        location = query["location"]
        print(f"[{qi+1:2d}/{len(queries)}] {keywords:30s} @ {location}...", flush=True)

        qi_ret, total, unique, new, errors, failed = await run_single_query(
            qi, len(queries), keywords, location, db_path
        )

        if errors < 3:
            _set_checkpoint(db_path, qi)
            print(f"    => {unique} unique, {new} new, errors={errors}")
            if failed:
                print(f"       Failed sources: {failed}")
            total_new += new
            total_seen += unique - new
        else:
            print(f"    => ALL SOURCES FAILED: {failed}")

        total_errors += errors

        # Small delay between queries
        await asyncio.sleep(random.uniform(0.5, 1.5))

    print()
    print(f"[*] Cycle complete:")
    print(f"    New jobs:       {total_new}")
    print(f"    Already seen:  {total_seen}")
    print(f"    Query errors: {total_errors}")


# ── Single-query subprocess entry point ──────────────────────────────────────

async def run_query_in_subprocess(keywords: str, location: str, db_path: str) -> tuple[int, int, int, str]:
    """Run one query and print unique,new,errors to stdout. Used by the subprocess."""
    from jobs_finder.infrastructure.infojobs.scraper import (
        InfoJobsPlaywrightScraper,
        InfoJobsScraperSettings,
    )
    from jobs_finder.infrastructure.infojobs.throttle import InfoJobsAsyncThrottle
    from jobs_finder.infrastructure.indeed.scraper import (
        IndeedPlaywrightScraper,
        IndeedScraperSettings,
    )
    from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle
    from jobs_finder.infrastructure.linkedin.scraper import (
        LinkedInPlaywrightScraper,
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle as LinkedInAsyncThrottle
    from jobs_finder.infrastructure.linkedin.auth_cookie import (
        MultiEnvLinkedInAuthCookiesAdapter,
    )
    from jobs_finder.infrastructure.location.hardcoded_resolver import (
        HardcodedLocationResolver,
    )
    from jobs_finder.infrastructure.persistence.sqlite_job_repository import (
        SqliteJobRepository,
    )
    from playwright_stealth import Stealth  # type: ignore[import-untyped]

    settings = Settings()

    # Build scrapers
    li_throttle = LinkedInAsyncThrottle(min_interval_seconds=settings.throttle_seconds)
    li_settings = LinkedInScraperSettings(
        user_agent=settings.user_agent,
        timeout_ms=settings.request_timeout_ms,
        headless=settings.headless,
        max_pages=settings.linkedin_max_pages,
        inter_page_delay_seconds=settings.linkedin_inter_page_delay_seconds,
        xvfb_display=settings.linkedin_xvfb_display,
        launch_channel=settings.linkedin_launch_channel,
    )
    li_kwargs: dict = {}
    if settings.linkedin_li_at is not None:
        li_kwargs["auth_cookies"] = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=settings.linkedin_li_at,
            jsessionid=settings.linkedin_jsessionid,
            bcookie=settings.linkedin_bcookie,
            bscookie=settings.linkedin_bscookie,
            li_gc=settings.linkedin_li_gc,
        )
    li_scraper = LinkedInPlaywrightScraper(
        throttle=li_throttle,
        settings=li_settings,
        **li_kwargs,
    )

    indeed_throttle = IndeedAsyncThrottle(min_interval_seconds=settings.indeed_throttle_seconds)
    indeed_settings = IndeedScraperSettings(
        user_agent=settings.indeed_user_agent,
        timeout_ms=settings.indeed_timeout_ms,
        domain=settings.indeed_domain,
        max_pages=settings.indeed_max_pages,
        inter_page_delay_seconds=settings.indeed_inter_page_delay_seconds,
    )
    indeed_scraper = IndeedPlaywrightScraper(
        throttle=indeed_throttle,
        settings=indeed_settings,
    )

    ij_throttle = InfoJobsAsyncThrottle(min_interval_seconds=settings.infojobs_throttle_seconds)
    ij_settings = InfoJobsScraperSettings(
        user_agent=settings.infojobs_user_agent,
        timeout_ms=settings.infojobs_timeout_ms,
        domain=settings.infojobs_domain,
        max_pages=settings.infojobs_max_pages,
        inter_page_delay_seconds=settings.infojobs_inter_page_delay_seconds,
        launch_channel=settings.infojobs_launch_channel,
        chromium_path=settings.infojobs_chromium_path,
        location_resolver=HardcodedLocationResolver(),
    )
    ij_scraper = InfoJobsPlaywrightScraper(
        throttle=ij_throttle,
        settings=ij_settings,
        stealth=Stealth(),
    )

    errors = 0
    failed_sources: list[str] = []
    all_jobs: list = []

    try:
        async with li_scraper as li, indeed_scraper as ind, ij_scraper as ij:
            try:
                li_jobs = await li.search(keywords, location, limit=50)
                all_jobs.extend(li_jobs)
            except Exception as e:
                failed_sources.append("LinkedIn")
                errors += 1

            try:
                indeed_jobs = await ind.search(keywords, location, limit=50)
                all_jobs.extend(indeed_jobs)
            except Exception as e:
                failed_sources.append("Indeed")
                errors += 1

            try:
                ij_jobs = await ij.search(keywords, location, limit=50)
                all_jobs.extend(ij_jobs)
            except Exception as e:
                failed_sources.append("InfoJobs")
                errors += 1
    except Exception as e:
        failed_sources.extend(["LinkedIn", "Indeed", "InfoJobs"])
        errors += 3

    failed_str = "|".join(failed_sources)
    if errors == 3:
        return 0, 0, 3, failed_str

    # Deduplicate
    seen = set()
    unique_jobs: list = []
    for job in all_jobs:
        key = (job.source, job.id)
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    # Persist
    query_snapshot = {"keywords": keywords, "location": location}
    async with SqliteJobRepository(db_path=db_path) as repo:
        if unique_jobs:
            await repo.upsert_jobs(unique_jobs, query_snapshot=query_snapshot)

    return len(unique_jobs), len(unique_jobs), errors, failed_str


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query-only", action="store_true")
    parser.add_argument("--qi", type=int)
    parser.add_argument("--total", type=int)
    parser.add_argument("--keywords", type=str)
    parser.add_argument("--location", type=str)
    parser.add_argument("--db", type=str)
    args = parser.parse_args()

    if args.query_only:
        unique, new, errors, failed = asyncio.run(
            run_query_in_subprocess(args.keywords, args.location, args.db)
        )
        print(f"{unique},{new},{errors},{failed}")
        sys.exit(0 if errors < 3 else 1)
    else:
        asyncio.run(run_cycle())
