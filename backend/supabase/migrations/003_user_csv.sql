-- =============================================================================
-- jobs-finder — User CSV storage migration
-- =============================================================================
--
-- Run this migration on your Supabase project's SQL Editor:
--   1. Go to Supabase Dashboard → SQL Editor
--   2. Paste this content and run
--
-- Or via Supabase CLI:
--   supabase migration new user_csv
--   # paste this content
--   supabase db push
-- =============================================================================

-- ── Table: user_csv ───────────────────────────────────────────────────────────
-- Tracks generated CV PDFs per authenticated user.
CREATE TABLE IF NOT EXISTS user_csv (
    id                SERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    storage_path      TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_csv_user_id
    ON user_csv(user_id);

CREATE INDEX IF NOT EXISTS idx_user_csv_created_at
    ON user_csv(created_at DESC);

-- ── Disable Realtime on user_csv ──────────────────────────────────────────────
-- This table stores file paths and should never be broadcast to clients.
ALTER PUBLICATION supabase_realtime DROP TABLE IF EXISTS user_csv;

-- ── RLS Policies ───────────────────────────────────────────────────────────────
ALTER TABLE user_csv ENABLE ROW LEVEL SECURITY;

-- Users can only access their own rows.
CREATE POLICY "Users can manage own csv files" ON user_csv
    FOR ALL USING (auth.uid() = user_id);

-- ── Comments ──────────────────────────────────────────────────────────────────
COMMENT ON TABLE user_csv IS 'Generated CV PDFs per authenticated user';
COMMENT ON COLUMN user_csv.storage_path IS 'Path in Supabase Storage or filesystem';
