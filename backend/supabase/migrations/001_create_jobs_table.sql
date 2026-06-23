-- =============================================================================
-- jobs-finder — Supabase / PostgreSQL schema migration
-- =============================================================================
--
-- Run this migration on your Supabase project's SQL Editor:
--   1. Go to Supabase Dashboard → SQL Editor
--   2. Paste this content and run
--
-- Or via Supabase CLI:
--   supabase migration new create_jobs_table
--   # paste this content
--   supabase db push
-- =============================================================================

-- Enable unaccent extension for case- and accent-insensitive searches.
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- ── Table: jobs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL CHECK (source IN ('linkedin', 'indeed', 'infojobs')),
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT NOT NULL,
    url             TEXT NOT NULL,
    description     TEXT,
    posted_at       TIMESTAMPTZ NOT NULL,
    query_snapshot  TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, source_id)
);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_source
    ON jobs (source);

CREATE INDEX IF NOT EXISTS idx_jobs_posted_at
    ON jobs (posted_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_source_source_id
    ON jobs (source, source_id);

-- ── Comments ─────────────────────────────────────────────────────────────────
COMMENT ON TABLE jobs IS 'Persisted job listings from all scraped sources';
COMMENT ON COLUMN jobs.source_id IS 'Platform-native job ID (unique per source)';
