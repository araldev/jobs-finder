-- =============================================================================
-- jobs-finder — Migration 20260721_0004: grant USAGE on billing sequences
-- =============================================================================
--
-- The billing_events PK is `bigserial`, which is backed by a Postgres
-- sequence (`public.billing_events_id_seq`). Any INSERT path needs
-- `USAGE` on the sequence to call `nextval()` for the auto-incrementing ID.
--
-- This migration mirrors migration 006 (which granted USAGE on EVERY public
-- sequence to all three roles). We re-grant explicitly here in case the
-- billing_events table is created before the broader grant runs, and as
-- documentation of the exact sequence the billing handler depends on.
--
-- Idempotent: GRANT statements are no-ops on re-apply.
-- =============================================================================

GRANT USAGE ON SEQUENCE public.billing_events_id_seq TO authenticated;
GRANT USAGE ON SEQUENCE public.billing_events_id_seq TO service_role;
