-- =============================================================================
-- jobs-finder — Migration 007: add WITH CHECK to user-table RLS policies
-- =============================================================================
--
-- Symptom: `POST /api/users/me/favorites` returns 500 with body
--   {"error":"new row violates row-level security policy for table
--   \"user_favorites\""}
-- AFTER Migrations 005 (bigint) and 006 (sequence grants) already passed.
--
-- Root cause: The original RLS policy in Migration 002 was declared as
--   CREATE POLICY "Users can manage own favorites" ON user_favorites
--       FOR ALL USING (auth.uid() = user_id);
-- This is `FOR ALL USING (...)` WITHOUT a `WITH CHECK` clause. In
-- Postgres RLS semantics:
--   - `USING` gates SELECT/UPDATE/DELETE row visibility.
--   - `WITH CHECK` gates INSERT/UPDATE new-row validation.
-- When a policy has ONLY `USING` and no `WITH CHECK`, INSERTs are silently
-- rejected because there is no policy that says "allow this new row".
--
-- Why we're seeing this now: the earlier errors (int4 overflow, sequence
-- permission denied) aborted the INSERT before RLS even evaluated. With
-- those fixed, the request now reaches the RLS check, which fails.
--
-- Fix: recreate the user-table policies with both `USING` and
-- `WITH CHECK`. The `auth.uid() = user_id` predicate is identical for
-- both, so we can keep the same policy name.
--
-- Risk: zero. Recreating an equivalent policy is safe. Existing rows are
-- unaffected (RLS only gates writes).
--
-- The frontend INSERT also needs to include `user_id` explicitly (it was
-- relying on RLS to "auto-fill" it, which doesn't work). That change goes
-- in the frontend Route Handler — separate commit.
-- =============================================================================

-- ── user_favorites ────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "Users can manage own favorites" ON public.user_favorites;
CREATE POLICY "Users can manage own favorites" ON public.user_favorites
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ── user_engagement ──────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "Users can manage own engagement" ON public.user_engagement;
CREATE POLICY "Users can manage own engagement" ON public.user_engagement
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ── user_csv ─────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "Users can manage own csv files" ON public.user_csv;
CREATE POLICY "Users can manage own csv files" ON public.user_csv
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- Verification query (run after to confirm):
--   SELECT tablename, policyname, cmd, qual, with_check
--   FROM pg_policies
--   WHERE schemaname = 'public'
--     AND tablename IN ('user_favorites', 'user_engagement', 'user_csv')
--   ORDER BY tablename, policyname;
-- Expect: each policy shows non-null `qual` AND non-null `with_check`.
-- =============================================================================