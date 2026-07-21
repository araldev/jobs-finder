import "server-only";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Server-only Supabase client that uses the SERVICE_ROLE_KEY.
 *
 * This client BYPASSES RLS entirely — it is the seam between the Next.js
 * server runtime and Supabase for operations that require direct database
 * access without a user JWT (webhook UPSERT, billing event append).
 *
 * Usage: only in Route Handlers that handle Stripe webhooks or other
 * server-to-server calls. Do NOT import this in client components.
 *
 * The `server-only` import ensures this module cannot be bundled into the
 * browser JS chunk.
 */
let _serviceClient: SupabaseClient | null = null;

export function getServiceRoleClient(): SupabaseClient {
  if (_serviceClient) return _serviceClient;

  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!serviceRoleKey) {
    throw new Error(
      "SUPABASE_SERVICE_ROLE_KEY is not set. " +
        "The billing webhook and server-side subscription lookups require " +
        "a service-role client. Set SUPABASE_SERVICE_ROLE_KEY in frontend/.env.local.",
    );
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_SUPABASE_URL is not set.");
  }

  _serviceClient = createClient(url, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });

  return _serviceClient;
}
