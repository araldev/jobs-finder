# Supabase — local stack + dashboard SQL workflow

This directory holds the SQL migrations applied to the Supabase project
that backs `jobs-finder`. There are two ways to apply them:

1. **Local stack** (`supabase start`) — the recommended workflow for
   contributors. The `supabase` CLI runs Postgres + GoTrue +
   PostgREST + Storage locally; `supabase db push` applies every
   file under `migrations/` in order.
2. **Dashboard SQL editor** — for projects that don't use the CLI
   (i.e. dashboard-managed schemas). Paste each migration file into
   the SQL editor and run it by hand.

The `auth-flows` change adds two migrations:

- `migrations/20260621_0001_delete_current_user_rpc.sql` —
  `public.delete_current_user()` RPC used by the browser's
  account-deletion flow (Feature C).
- (Optional) `migrations/20260621_0002_user_csv_cascade_fk.sql` —
  applied ONLY if the dashboard audit shows `user_csv.user_id` lacks
  `ON DELETE CASCADE`. Verify before writing.

## ⚠️ IRREVERSIBILITY

`delete_current_user()` is a Postgres `SECURITY DEFINER` function that
hard-deletes the calling user's `auth.users` row. Once applied, an
`auth.users` row is GONE — there is no soft-delete and no recovery
path. The product contract is GDPR — no take-backs. Re-creating the
account requires a fresh sign-up with a new email.

The function body is structured to minimize blast radius when invoked:

1. `IF auth.uid() IS NULL THEN RAISE EXCEPTION 'not authenticated'` —
   rejects anonymous callers (BOLA defense).
2. `DELETE FROM storage.objects WHERE bucket_id = 'cvs' AND …` —
   removes the user's CV objects under `${uid}/`.
3. `DELETE FROM public.user_csv WHERE user_id = …` — removes the
   per-user row.
4. `DELETE FROM auth.users WHERE id = …` — cascades to any future
   table with `ON DELETE CASCADE` FK to `auth.users`.

The function is **idempotent** on re-call (a second invocation is a
no-op — no rows match, function returns `void`, no error).

## Apply via local stack (`supabase start`)

```bash
# One-time per machine
brew install supabase/tap/supabase   # macOS
# or: https://github.com/supabase/cli#install-the-cli

cd backend
supabase start                      # boots Postgres + GoTrue + PostgREST + Storage + Inbucket
supabase db push                    # applies every migration under supabase/migrations/
```

After `supabase start`, the local services are reachable at:

| Service     | URL                                |
| ----------- | ---------------------------------- |
| Postgres    | `postgresql://postgres:postgres@localhost:54322/postgres` |
| PostgREST   | `http://localhost:54321`           |
| GoTrue      | `http://localhost:54321/auth/v1`   |
| Storage     | `http://localhost:54321/storage/v1`|
| Studio      | `http://localhost:54323`           |
| **Inbucket**| `http://localhost:54324` (mail preview) |

Verify the function exists:

```sql
SELECT * FROM pg_proc WHERE proname = 'delete_current_user';
-- Expect 1 row.
```

## Apply via dashboard SQL editor

For projects that don't use the CLI:

1. Open the [Supabase dashboard](https://app.supabase.com) → your
   project → SQL editor → New query.
2. Open `migrations/20260621_0001_delete_current_user_rpc.sql` from
   this repo. Copy the entire contents into the query editor.
3. Click **Run** (or press `Ctrl/Cmd+Enter`). Expect: `Success. No
   rows returned`.
4. Verify: run `select * from pg_proc where proname =
   'delete_current_user';` in a new query — expect 1 row.
5. (Optional) Apply file 2 (`20260621_0002_user_csv_cascade_fk.sql`)
   only if the dashboard audit shows the `user_csv.user_id` FK is
   missing `ON DELETE CASCADE`. To audit: Table Editor →
   `public.user_csv` → foreign keys → inspect the `user_id` FK.

## Supabase dashboard configuration (no SQL)

The frontend code relies on Supabase Auth defaults — no SQL change
needed for these settings. Configure them in the dashboard:

### Authentication → URL Configuration

| Field                    | Value (dev)                          | Value (prod)                  |
| ------------------------ | ------------------------------------ | ----------------------------- |
| Site URL                 | `http://localhost:3000`              | `https://jobs-finder.app`     |
| Additional redirect URLs | `http://localhost:3000/auth/callback` + `https://jobs-finder.app/auth/callback` |  |

### Authentication → Providers → Email

- **Confirm email**: ON (the email-verification banner depends on this).
- **Secure password change**: defaults are fine.

### Authentication → Email Templates

The default templates are sufficient. To localize the sender name:

- **Authentication → Email Templates → Confirm signup**: sender name
  → `Jobs Finder`.
- **Authentication → Email Templates → Reset password**: sender
  name → `Jobs Finder`.
- **Authentication → Email Templates → Magic link**: sender name
  → `Jobs Finder`.

The body copy stays as Supabase default — Spanish product copy is
configured at the application level via `authCopy.ts`, not in the
email body.

### Storage → `cvs` bucket policies

The `cvs` bucket must allow:

- `SELECT` on `storage.objects` where `auth.uid()::text =
  (storage.foldername(name))[1]` (the user reads their own CVs).
- `INSERT` on `storage.objects` where `auth.uid()::text =
  (storage.foldername(name))[1]` (the user uploads to their prefix).
- `DELETE` on `storage.objects` where `auth.uid()::text =
  (storage.foldername(name))[1]` (the user removes their CV).

The `delete_current_user` RPC bypasses these policies via `SECURITY
DEFINER`, so the post-deletion cleanup works regardless of RLS state.

## Rollback

```sql
-- Remove the RPC entirely.
DROP FUNCTION IF EXISTS public.delete_current_user();

-- (If file 2 was applied) Revert the FK to its pre-cascade form.
ALTER TABLE public.user_csv
  DROP CONSTRAINT IF EXISTS user_csv_user_id_fkey;
```

`auth.users` rows hard-deleted by the RPC are NOT recoverable — see
the **IRREVERSIBILITY** callout above.

## Backend integration test (manual, NOT in CI)

`backend/tests/integration/test_delete_user_rpc.py` exercises the
RPC against `supabase start`. The `@pytest.mark.supabase_local`
marker auto-skips these tests in CI (no live Supabase calls). To run
them locally:

```bash
cd backend
SUPABASE_LOCAL_URL=http://localhost:54321 \
SUPABASE_LOCAL_ANON_KEY=$(supabase status | grep 'anon key' | awk '{print $NF}') \
SUPABASE_LOCAL_SERVICE_KEY=$(supabase status | grep 'service_role key' | awk '{print $NF}') \
  uv run pytest -m supabase_local tests/integration/test_delete_user_rpc.py -v
```

The current happy-path test is a smoke check (the full end-to-end
requires the `/auth/v1/token?grant_type=password` flow which is
out of scope for this change — see the function-level docstring).
