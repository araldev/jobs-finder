-- =============================================================================
-- jobs-finder — Fix user_csv FK to ON DELETE CASCADE
-- =============================================================================
--
-- Idempotent: alters the existing FK constraint on user_csv.user_id
-- (created manually or by a prior migration) to ON DELETE CASCADE.
-- Works around the fact that the original migration may have omitted CASCADE.
--
-- Run this migration on your Supabase project's SQL Editor:
--   1. Go to Supabase Dashboard → SQL Editor
--   2. Paste this content and run
--
-- Or via Supabase CLI:
--   supabase db push
-- =============================================================================

-- Drop the existing FK constraint if it exists (works regardless of name).
-- The FK may be named differently depending on how the table was created.
DO $$
DECLARE
    fk_name text;
BEGIN
    -- Find the foreign key constraint on user_csv.user_id referencing auth.users
    SELECT tc.constraint_name INTO fk_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
    WHERE tc.table_name = 'user_csv'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND ccu.column_name = 'user_id'
      AND ccu.table_name = 'auth.users'
    LIMIT 1;

    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE user_csv DROP CONSTRAINT %I', fk_name);
    END IF;
END $$;

-- Re-add with CASCADE
ALTER TABLE user_csv
    ADD CONSTRAINT user_csv_user_id_fkey
    FOREIGN KEY (user_id)
    REFERENCES auth.users(id)
    ON DELETE CASCADE;
