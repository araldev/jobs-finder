import { PageTransition } from "@/components/layout/PageTransition";

export default function AdaptCVLoading() {
  return (
    <PageTransition>
      <div className="mx-auto max-w-2xl">
        <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
          <div className="flex flex-col space-y-1.5 p-6">
            <div className="skeleton-shimmer h-7 w-64 rounded-lg" />
            <div className="skeleton-shimmer h-4 w-96 rounded-lg" />
          </div>
          <div className="space-y-5 p-6 pt-0">
            {/* File drop zone skeleton */}
            <div className="skeleton-shimmer h-32 w-full rounded-lg" />

            {/* URL input skeleton */}
            <div className="space-y-2">
              <div className="skeleton-shimmer h-4 w-24 rounded-lg" />
              <div className="skeleton-shimmer h-10 w-full rounded-lg" />
            </div>

            {/* Description textarea skeleton */}
            <div className="space-y-2">
              <div className="skeleton-shimmer h-4 w-32 rounded-lg" />
              <div className="skeleton-shimmer h-28 w-full rounded-lg" />
            </div>

            {/* Optional fields skeleton */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <div className="skeleton-shimmer h-4 w-28 rounded-lg" />
                <div className="skeleton-shimmer h-10 w-full rounded-lg" />
              </div>
              <div className="space-y-2">
                <div className="skeleton-shimmer h-4 w-20 rounded-lg" />
                <div className="skeleton-shimmer h-10 w-full rounded-lg" />
              </div>
            </div>

            {/* Consent skeleton */}
            <div className="skeleton-shimmer h-16 w-full rounded-lg" />

            {/* Button skeleton */}
            <div className="skeleton-shimmer h-10 w-full rounded-lg" />
          </div>
        </div>
      </div>
    </PageTransition>
  );
}
