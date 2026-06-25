-- =============================================================================
-- jobs-finder — Supabase RLS and Grants Fix
-- =============================================================================
--
-- PROBLEMA: Las migraciones habilitan RLS pero no otorgan permisos
-- explícitos al service_role. En Supabase, el service_role bypasses RLS
-- pero necesita permisos directos sobre las tablas.
--
-- SOLUCIÓN: Ejecutar este SQL en el SQL Editor de Supabase para otorgar
-- los permisos necesarios.
--
-- =============================================================================

-- ── grants para la tabla jobs ────────────────────────────────────────────────
-- El scheduler escribe jobs (via service_role), y los usuarios auth pueden leer.
-- Nadie debería modificar o eliminar jobs directamente.

-- Permisos para el service_role (backend scheduler)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.jobs TO service_role;

-- Permisos para usuarios autenticados (lectura)
GRANT SELECT ON public.jobs TO authenticated;
GRANT SELECT ON public.jobs TO anon;


-- ── grants para la tabla user_favorites ─────────────────────────────────────
GRANT SELECT, INSERT, DELETE ON public.user_favorites TO service_role;
GRANT SELECT, INSERT, DELETE ON public.user_favorites TO authenticated;
GRANT SELECT ON public.user_favorites TO anon;


-- ── grants para la tabla user_engagement ────────────────────────────────────
GRANT SELECT, INSERT ON public.user_engagement TO service_role;
GRANT SELECT, INSERT ON public.user_engagement TO authenticated;
GRANT SELECT ON public.user_engagement TO anon;


-- ── grants para la tabla user_settings ──────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON public.user_settings TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.user_settings TO authenticated;
GRANT SELECT ON public.user_settings TO anon;


-- ── grants para la tabla user_csv ───────────────────────────────────────────
GRANT SELECT, INSERT, DELETE ON public.user_csv TO service_role;
GRANT SELECT, INSERT, DELETE ON public.user_csv TO authenticated;
GRANT SELECT ON public.user_csv TO anon;


-- ── verificar grants ─────────────────────────────────────────────────────────
-- Ejecutar esto para verificar que los grants se aplicaron:
-- SELECT grantee, privilege_type, table_name FROM information_schema.table_privileges WHERE table_schema = 'public';


-- ── nota sobre RLS ──────────────────────────────────────────────────────────
-- Las políticas RLS ya están creadas en las migraciones:
--   - user_favorites: auth.uid() = user_id
--   - user_engagement: auth.uid() = user_id
--   - user_settings: auth.uid() = user_id
--   - user_csv: auth.uid() = user_id
--
-- La tabla jobs NO tiene políticas RLS porque es data pública scrapeada.
-- El service_role tiene acceso completo a jobs bypassing RLS.
