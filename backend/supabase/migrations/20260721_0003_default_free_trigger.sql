-- =============================================================================
-- jobs-finder — Migration 20260721_0003: default-Free trigger on auth.users
-- =============================================================================
--
-- On every new `auth.users` row, this AFTER INSERT trigger fires a
-- SECURITY DEFINER function that INSERTs a `subscriptions(plan='free',
-- status='active')` row for the new user. This is how the product gets
-- "default-Free access" without every consumer having to handle the
-- "no row found" case (REQ-BILL-SUBS-001).
--
-- Why SECURITY DEFINER:
--   The trigger runs in the context of the inserting principal (e.g. an
--   `anon` signup via GoTrue). Without SECURITY DEFINER, the INSERT into
--   `public.subscriptions` would FAIL with "permission denied for table
--   subscriptions" (the RLS policy allows SELECT only, not INSERT for
--   authenticated/anon). SECURITY DEFINER elevates to the function owner
--   (typically `postgres`), bypassing RLS for the INSERT.
--
-- Why the `pg_trigger_depth()` guard:
--   If a future migration adds a trigger on `public.subscriptions` that
--   itself touches `auth.users`, we'd recurse forever. The guard rejects
--   nested calls (depth > 0) so the recursion is impossible by construction.
--
-- Idempotent: `DROP TRIGGER IF EXISTS` + `CREATE OR REPLACE FUNCTION` make
-- re-application safe (the manual SQL workflow may double-apply).
-- =============================================================================

CREATE OR REPLACE FUNCTION public.default_free_subscription()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
begin
    -- Bail on nested trigger calls (defense against future trigger cycles).
    if pg_trigger_depth() <> 1 then
        return new;
    end if;

    insert into public.subscriptions (user_id, plan, status)
    values (new.id, 'free', 'active')
    on conflict (user_id) do nothing;

    return new;
end;
$$;

COMMENT ON FUNCTION public.default_free_subscription() IS
    'AFTER INSERT trigger on auth.users — auto-creates a Free subscription row.';

-- Drop first so the migration is idempotent (defensive — the trigger may
-- already exist from a prior apply).
DROP TRIGGER IF EXISTS trg_default_free_subscription ON auth.users;

CREATE TRIGGER trg_default_free_subscription
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.default_free_subscription();

COMMENT ON TRIGGER trg_default_free_subscription ON auth.users IS
    'Auto-creates subscriptions(plan=free, status=active) on signup.';

-- ── Grants ──────────────────────────────────────────────────────────────────
-- The function is owned by `postgres` (or whoever ran the migration).
-- EXECUTE is granted to `authenticated` so any client-side INSERT into
-- `auth.users` (via GoTrue's signUp RPC) triggers the row-creation.
-- (In practice the trigger fires regardless of grants because triggers
--  execute under the function owner's context, but this is explicit.)
GRANT EXECUTE ON FUNCTION public.default_free_subscription() TO authenticated;
GRANT EXECUTE ON FUNCTION public.default_free_subscription() TO service_role;
