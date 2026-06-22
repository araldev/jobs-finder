import Link from "next/link";
import Image from "next/image";
import type { ReactNode } from "react";

/**
 * Public auth layout — wraps /login, /signup, /forgot-password,
 * /reset-password with a centered logo + card chrome. The (app)
 * layout (AppShell + sidebar + header) is NOT used here; these
 * pages render standalone.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-8">
      <Link href="/" className="mb-8 inline-flex items-center gap-2">
        <Image
          src="/favicon.svg"
          alt="Jobs Finder"
          width={36}
          height={36}
          className="h-9 w-9"
        />
        <span className="font-display text-xl font-bold">Jobs Finder</span>
      </Link>
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-sm">
        {children}
      </div>
    </div>
  );
}
