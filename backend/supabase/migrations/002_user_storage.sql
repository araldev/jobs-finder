-- =============================================================================
-- jobs-finder — User storage migration
-- =============================================================================
--
-- Run this migration on your Supabase project's SQL Editor:
--   1. Go to Supabase Dashboard → SQL Editor
--   2. Paste this content and run
--
-- Or via Supabase CLI:
--   supabase migration new user_storage
--   # paste this content
--   supabase db push
-- =============================================================================

-- Enable UUID extension for user_id columns.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Table: user_favorites ────────────────────────────────────────────────────
-- Many-to-many relationship between auth.users and jobs.
CREATE TABLE IF NOT EXISTS user_favorites (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id
    ON user_favorites(user_id);

CREATE INDEX IF NOT EXISTS idx_user_favorites_job_id
    ON user_favorites(job_id);

CREATE INDEX IF NOT EXISTS idx_user_favorites_created_at
    ON user_favorites(created_at DESC);

-- ── Table: user_engagement ────────────────────────────────────────────────────
-- Raw engagement event log per user.
CREATE TABLE IF NOT EXISTS user_engagement (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL CHECK (event_type IN ('job_view', 'job_click', 'search', 'cv_adapted')),
    job_id      INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_engagement_user_id
    ON user_engagement(user_id);

CREATE INDEX IF NOT EXISTS idx_user_engagement_created_at
    ON user_engagement(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_engagement_event_type
    ON user_engagement(event_type);

-- ── Table: user_settings ──────────────────────────────────────────────────────
-- Per-user preferences.
CREATE TABLE IF NOT EXISTS user_settings (
    user_id                 UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    enabled_platforms       TEXT[] NOT NULL DEFAULT ARRAY['linkedin', 'indeed', 'infojobs'],
    notifications_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── RLS Policies ───────────────────────────────────────────────────────────────
-- Enable Row Level Security on user tables.
ALTER TABLE user_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_engagement ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

-- Users can only access their own rows.
CREATE POLICY "Users can manage own favorites" ON user_favorites
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own engagement" ON user_engagement
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own settings" ON user_settings
    FOR ALL USING (auth.uid() = user_id);

-- ── Comments ──────────────────────────────────────────────────────────────────
COMMENT ON TABLE user_favorites IS 'Favorited jobs per authenticated user';
COMMENT ON TABLE user_engagement IS 'Raw engagement event log per authenticated user';
COMMENT ON TABLE user_settings IS 'Per-user preferences and platform configuration';
