-- =============================================================================
-- jobs-finder — Migration 20260721_0002: billing_events audit log
-- =============================================================================
--
-- Append-only audit of every Stripe webhook event the backend received.
-- The webhook handler INSERTs one row per `event_id` it processes; the
-- `event_id` UNIQUE constraint gives us idempotent replay (a duplicate
-- INSERT raises ON CONFLICT, the handler returns 200 without applying
-- state changes).
--
-- Columns:
--   id            — SERIAL PK (auto-increment; consumer is backend-only)
--   event_id      — Stripe's `evt_...` ID; UNIQUE for replay safety
--   event_type    — e.g. 'checkout.session.completed',
--                   'customer.subscription.updated', etc.
--   payload       — full Stripe Event object as JSONB (for forensics)
--   received_at   — when our webhook handler received it (UTC)
--   processed_at  — when we successfully applied state (NULL if we deferred)
--
-- RLS:
--   - NO policies for `authenticated` — clients CANNOT read billing_events.
--     This keeps Stripe's payload off the wire (it includes customer email,
--     price IDs, raw metadata, etc.) and matches the spec's append-only
--     constraint (REQ-BILL-SUBS-001: "billing_events MUST be append-only").
--   - `service_role` can SELECT/INSERT (handler is the only writer; an
--     admin script can read for audits).
--
-- Grants:
--   - SELECT to `service_role` only (no `authenticated` grant on purpose)
--   - INSERT to `service_role` only
--   - USAGE on the underlying sequence for both roles (so a future RPC can
--     insert without permission-denied errors)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.billing_events (
    id            bigserial PRIMARY KEY,
    event_id      text NOT NULL UNIQUE,
    event_type    text NOT NULL,
    payload       jsonb NOT NULL,
    received_at   timestamptz NOT NULL DEFAULT now(),
    processed_at  timestamptz
);

COMMENT ON TABLE public.billing_events IS
    'Append-only audit log of Stripe webhook events (no UPDATE / no DELETE policy).';
COMMENT ON COLUMN public.billing_events.event_id IS
    'Stripe Event ID (`evt_...`). UNIQUE — replays raise ON CONFLICT and the handler skips.';
COMMENT ON COLUMN public.billing_events.payload IS
    'Full Stripe Event object as JSONB. Includes customer email + raw metadata — NEVER expose via RLS.';

-- Index for the handler's primary lookup path (replay dedup).
CREATE INDEX IF NOT EXISTS idx_billing_events_event_id
    ON public.billing_events (event_id);

-- Index for ops queries (e.g. "show me all payment_failed events in the
-- last 7 days"). event_type + received_at descending.
CREATE INDEX IF NOT EXISTS idx_billing_events_type_received_at
    ON public.billing_events (event_type, received_at DESC);

-- ── RLS ─────────────────────────────────────────────────────────────────────
ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;

-- Explicitly NO policies for `authenticated` — clients cannot read this table.
-- `service_role` bypasses RLS so it can SELECT/INSERT without a policy.

-- ── Grants ──────────────────────────────────────────────────────────────────
-- service_role: full control (the only writer; an ops script can read).
GRANT SELECT, INSERT ON public.billing_events TO service_role;

-- The bigserial PK needs sequence USAGE for any future INSERT path.
GRANT USAGE ON SEQUENCE public.billing_events_id_seq TO service_role;
