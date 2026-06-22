import { Skeleton } from "@/components/ui/skeleton";

/**
 * `/search` instant loading boundary (REQ-CACHEUX-005).
 *
 * RSC (no `"use client"` directive) — ships zero client JS. Mirrors
 * the real `/search` page's grid shape
 * (`lg:grid-cols-2 xl:grid-cols-3` + `h-[180px] rounded-xl`) so the
 * layout doesn't shift when the real page swaps in.
 *
 * Next.js shows this UI within 100ms of clicking the landing
 * `<Link href="/search">` (the default `prefetch={true}` streams
 * the RSC payload as soon as the link enters the viewport).
 */
export default function SearchLoading() {
  return (
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 9 }).map((_, i) => (
        <Skeleton key={i} className="h-[180px] rounded-xl" />
      ))}
    </div>
  );
}
