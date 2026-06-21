-- delete_current_user RPC (REQ-AUTH-009 / REQ-AUTH-010)
--
-- Hard-delete the calling user's account, their CV storage objects,
-- and their user_csv row, then the auth.users row itself.
--
-- SECURITY DEFINER so it can DELETE from auth.users and storage.objects.
-- The first statement is an auth.uid() guard — anonymous callers are
-- rejected with a Postgres exception (errcode 28000 = "no privilege"
-- / "not authenticated"). The function is granted EXECUTE only to the
-- `authenticated` role (NOT anon, NOT public).
--
-- Idempotent: a second call on the same UID is a no-op (no rows match,
-- function returns void, no error).
--
-- ⚠️  IRREVERSIBLE once applied. The auth.users row is hard-deleted by
--     this function; there is no soft-delete and no recovery path.
--     The product contract is GDPR — no take-backs.
--
-- Apply this migration via one of:
--   1. `supabase db push` (recommended for projects using the CLI).
--   2. The Supabase dashboard SQL editor — paste-and-run. See
--      `backend/supabase/README.md` for the manual steps.

create or replace function public.delete_current_user()
returns void
language plpgsql
security definer
set search_path = public, storage, auth
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  -- (a) Storage objects in the `cvs` bucket under {uid}/ prefix.
  delete from storage.objects
    where bucket_id = 'cvs'
      and (storage.foldername(name))[1] = v_uid::text;

  -- (b) user_csv rows for this user.
  delete from public.user_csv
    where user_id = v_uid;

  -- (c) auth.users row. Cascades to any future table with
  -- `on delete cascade` FK to auth.users (the `user_csv.user_id`
  -- FK should be ON DELETE CASCADE — see the second migration file).
  delete from auth.users
    where id = v_uid;
end;
$$;

revoke all on function public.delete_current_user() from public;
grant execute on function public.delete_current_user() to authenticated;
