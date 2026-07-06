-- =============================================================================
-- jobs-finder — Migration 005: fix int4 overflow on LinkedIn job_id columns
-- =============================================================================
--
-- Symptom: `POST /api/users/me/favorites` returns 500 with body
--   {"error":"value \"4432827022\" is out of range for type integer"}
-- whenever the user favorites a LinkedIn job whose ID is > 2_147_483_647
-- (the max of `int4`).
--
-- Root cause: `user_favorites.job_id`, `user_engagement.job_id`, and
-- `jobs.id` were all declared as `INTEGER` (`int4` in Postgres, max
-- 2_147_483_647). LinkedIn job IDs are 10-digit numbers already above that.
--
-- Pre-flight verification (run BEFORE the migration to confirm the diagnosis):
--   SELECT table_name, column_name, data_type
--   FROM information_schema.columns
--   WHERE (table_name = 'jobs' AND column_name = 'id')
--      OR (table_name IN ('user_favorites', 'user_engagement') AND column_name = 'job_id')
--   ORDER BY table_name, column_name;
-- Expect all three rows show `integer`.
--
-- Fix: widen all three columns to `BIGINT` (int8). FK constraints follow
-- automatically when `jobs.id` is widened first.
--
-- Order matters: parent table (`jobs.id`) MUST be widened before child
-- FKs (`user_favorites.job_id`, `user_engagement.job_id`).
--
-- Risk: zero — `ALTER COLUMN TYPE` between int4 and int8 in Postgres 12+
-- is a catalog-only rewrite (no row rewrite, no table rewrite). The FK
-- constraints are updated atomically with the type change.
-- =============================================================================

-- 1) Parent: jobs.id (every FK to it depends on this type).
ALTER TABLE public.jobs
    ALTER COLUMN id TYPE BIGINT;

-- 2) Child: user_favorites.job_id (FK to jobs.id, ON DELETE CASCADE).
ALTER TABLE public.user_favorites
    ALTER COLUMN job_id TYPE BIGINT;

-- 3) Child: user_engagement.job_id (FK to jobs.id, nullable, ON DELETE SET NULL).
ALTER TABLE public.user_engagement
    ALTER COLUMN job_id TYPE BIGINT;

-- =============================================================================
-- Verification query (run after to confirm):
--   SELECT table_name, column_name, data_type
--   FROM information_schema.columns
--   WHERE (table_name = 'jobs' AND column_name = 'id')
--      OR (table_name IN ('user_favorites', 'user_engagement') AND column_name = 'job_id')
--   ORDER BY table_name, column_name;
-- Expect all three rows show `bigint`.
-- =============================================================================
