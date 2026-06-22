"use client";

/**
 * `useCurrentUser` — REQ-PDPRSC-004.
 *
 * Shared React Query hook that fetches the current Supabase user
 * once per cache window (5min staleTime) and shares the result
 * across every consumer on the page. Before this hook existed,
 * `EmailVerificationBanner` and `AuthStatus` each called
 * `supabase.auth.getUser()` / `supabase.auth.getSession()` on
 * mount, causing two simultaneous `/auth/v1/user` requests on
 * every dashboard load.
 *
 * The contract:
 *
 *   - Two consumers sharing one `QueryClient` trigger ONE
 *     `supabase.auth.getUser()` call (SCN-PDPRSC-004-A) — this
 *     is the React Query queryKey dedup, applied at the
 *     framework level.
 *   - `staleTime` is exactly 5 minutes (SCN-PDPRSC-004-B) — so
 *     navigations within 5min never refetch.
 *   - `refetchOnWindowFocus: true` is the default from
 *     `Providers.tsx:15`, kept explicit here so the contract
 *     is local to the hook.
 *
 * The `select: (data) => data.data.user` extractor flattens the
 * supabase wrapper so consumers receive `User | null` directly,
 * matching what `EmailVerificationBanner` and `AuthStatus` need.
 *
 * The `supabase.auth.onAuthStateChange` subscription is set up
 * inside `useEffect` (per hook mount) so each consumer gets
 * its own subscription lifecycle — the subscription is cheap
 * and React's effect cleanup ensures it doesn't leak. The
 * subscriber calls `queryClient.invalidateQueries({ queryKey })`
 * on every auth event, so sign-in / sign-out / token-refresh
 * triggers a refetch on the next render frame (SCN-004-E).
 *
 * Module-level fetch function (`fetchCurrentUser`) instead of
 * an inline closure so the queryFn identity stays stable across
 * renders — important for `useQuery` to avoid re-subscribing
 * the queryFn on every render.
 */

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";

export const CURRENT_USER_QUERY_KEY = ["current-user"] as const;

async function fetchCurrentUser() {
  const supabase = createClient();
  const { data, error } = await supabase.auth.getUser();
  if (error) throw error;
  return data;
}

export function useCurrentUser() {
  const queryClient = useQueryClient();
  const supabase = createClient();

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(() => {
      // Invalidate the cache on every auth event (SIGNED_IN,
      // SIGNED_OUT, TOKEN_REFRESHED, USER_UPDATED). The next
      // consumer mount or the next refetch-on-focus will pull
      // fresh user state.
      queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
    });
    return () => subscription.unsubscribe();
  }, [supabase, queryClient]);

  return useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: fetchCurrentUser,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
    select: (data) => data.user,
  });
}