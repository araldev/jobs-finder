-- =============================================================================
-- jobs-finder — Migration 20260721_0001: subscriptions table
-- =============================================================================
--
-- Adds the durable source of truth for plan lookup. The browser reads this
-- table via the Next.js service-role Supabase client (`@/lib/supabase/
-- service-role`) on every `/api/billing/subscription` request (with a 60s
-- in-memory cache). The Stripe webhook handler UPSERTs into this table.
--
-- Three plans are accepted by the CHECK constraint per design D7 — Pro Plus
-- is a future-proof schema slot; no UI flow ever sets it. The
-- `default-free-trigger` migration auto-inserts `(plan='free', status='active')`
-- when a new `auth.users` row is created.
--
-- Columns:
--   user_id              — PK, FK to auth.users(id), ON DELETE CASCADE
--   plan                 — 'free' | 'pro' | 'pro_plus' (CHECK constraint)
--   status               — 'active' | 'trialing' | 'past_due' | 'canceled'
--   stripe_customer_id   — UNIQUE; nullable (NULL for users who never hit Stripe)
--   stripe_subscription_id — UNIQUE; nullable (NULL until first checkout)
--   current_period_end   — ISO timestamptz from Stripe (UTC)
--   trial_end            — ISO timestamptz (NULL unless status='trialing')
--   cancel_at_period_end — boolean; flips to true when the user cancels via Portal
--   created_at / updated_at — standard timestamp columns
--
-- RLS:
--   - authenticated users can SELECT their own row only (auth.uid() = user_id)
--   - NO INSERT/UPDATE policy for `authenticated` — the webhook handler uses
--     the service-role client, which bypasses RLS deterministically. This
--     keeps the schema DRY (no `WITH CHECK` for the client to bypass).
--
-- Grants:
--   - SELECT to `authenticated` (matches RLS — they only see their own row)
--   - ALL    to `service_role`  (webhook handler can UPSERT without a JWT)
--
-- Idempotent: each statement is wrapped in `IF NOT EXISTS` so re-applying is a
-- no-op (defensive — the manual SQL workflow may double-apply).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.subscriptions (
    user_id                 uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    plan                    text NOT NULL DEFAULT 'free'
                            CHECK (plan IN ('free', 'pro', 'pro_plus')),
    status                  text NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'trialing', 'past_due', 'canceled')),
    stripe_customer_id      text UNIQUE,
    stripe_subscription_id  text UNIQUE,
    current_period_end      timestamptz,
    trial_end               timestamptz,
    cancel_at_period_end    boolean NOT NULL DEFAULT false,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.subscriptions IS
    'Per-user plan state. Source of truth for /api/billing/subscription.';
COMMENT ON COLUMN public.subscriptions.plan IS
    'free | pro | pro_plus. Pro Plus is reserved for a future upgrade.';
COMMENT ON COLUMN public.subscriptions.status IS
    'active | trialing | past_due | canceled. Matches Stripe subscription.status.';

-- Index for the Stripe webhook handler (lookup by customer ID is the hot path
-- on every customer.subscription.* event). Partial index — most users will
-- never have a stripe_customer_id (Free users).
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer
    ON public.subscriptions (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- Index for the webhook's subscription-id lookup (also hot on every event).
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription
    ON public.subscriptions (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

-- ── RLS ─────────────────────────────────────────────────────────────────────
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

-- "users_can_read_own_sub" — the ONLY policy. Read-only for clients.
-- Service-role bypasses RLS, so the webhook handler can UPSERT without a JWT.
DROP POLICY IF EXISTS "users_can_read_own_sub" ON public.subscriptions;
CREATE POLICY "users_can_read_own_sub" ON public.subscriptions
    FOR SELECT
    USING (auth.uid() = user_id);

-- ── Grants ──────────────────────────────────────────────────────────────────
GRANT SELECT ON public.subscriptions TO authenticated;
GRANT ALL    ON public.subscriptions TO service_role;
