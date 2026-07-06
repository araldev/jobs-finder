-- =============================================================================
-- jobs-finder — Migration 006: grant USAGE on all public schema sequences
-- =============================================================================
--
-- Symptom: `POST /api/users/me/favorites` returns 500 with body
--   {"error":"permission denied for sequence user_favorites_id_seq"}
-- after Migration 005 widened the column types. Saving a favorite fails
-- at INSERT time even though the row + RLS are now correctly typed,
-- because `SERIAL PRIMARY KEY` columns need `USAGE` on the underlying
-- sequence to call `nextval()` for the auto-incrementing ID.
--
-- Root cause: Migration 004 (`004_fix_rls_grants.sql`) granted the right
-- privileges on the TABLES (`user_favorites`, `user_engagement`, `user_csv`)
-- but never granted on the SEQUENCES that back their `SERIAL PRIMARY KEY`
-- columns (`user_favorites_id_seq`, `user_engagement_id_seq`,
-- `user_csv_id_seq`). This was a latent bug ever since Migration 002/003
-- created the tables — it just was never exercised before because the
-- int4-overflow bug aborted the INSERT first.
--
-- Fix: grant `USAGE` on ALL sequences in the `public` schema to the three
-- roles that hit them (`authenticated`, `anon`, `service_role`). The
-- `ON ALL SEQUENCES` form automatically covers any future SERIAL/BIGSERIAL
-- column added to the public schema — defense in depth.
--
-- Idempotent: safe to run multiple times.
--
-- Risk: zero. Granting USAGE on sequences is non-blocking, does not
-- touch table or row data, and only relaxes permission denials.
-- =============================================================================

-- Apply USAGE to every existing AND future sequence in the public schema.
-- `GRANT ... ON ALL SEQUENCES` covers the three known SERIAL-backed PKs
-- plus anything added later (BIGSERIAL on new tables, etc.).
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO anon;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- =============================================================================
-- Verification query (run after to confirm):
--   SELECT grantee, object_schema, object_name, privilege_type
--   FROM information_schema.role_usage_grants
--   WHERE object_schema = 'public'
--     AND object_name LIKE '%_id_seq'
--   ORDER BY object_name, grantee, privilege_type;
-- Expect: at least three rows per role covering the three sequences above.
-- =============================================================================