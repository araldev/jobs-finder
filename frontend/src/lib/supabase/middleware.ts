import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Rutas públicas: / (landing page), /jobs (detalle público), /login, /signup, /auth
  // APIs (/api/*) son siempre accesibles. /forgot-password and /reset-password
  // are part of the public auth flow (REQ-AUTH-021) so an unauthenticated
  // user can request + complete a password reset without bouncing to /login.
  const publicPaths = ["/jobs", "/login", "/signup", "/auth", "/forgot-password", "/reset-password"];
  const isPublic = publicPaths.some((path) =>
    request.nextUrl.pathname.startsWith(path),
  );

  // La raíz / es la landing page pública
  const isRoot = request.nextUrl.pathname === "/";

  // Las APIs son siempre accesibles
  const isApi = request.nextUrl.pathname.startsWith("/api");

  // Si la ruta NO es pública, NO es la raíz, NO es API, y NO hay usuario → redirect a /login
  if (!user && !isPublic && !isRoot && !isApi) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Si está logueado y va a /login → redirect a /dashboard
  if (user && request.nextUrl.pathname.startsWith("/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
