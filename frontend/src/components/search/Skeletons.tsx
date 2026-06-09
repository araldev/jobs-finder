import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Six skeleton cards matching the responsive grid layout. */
export function SearchSkeletons(): React.ReactElement {
  return (
    <ul
      aria-hidden
      className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
    >
      {Array.from({ length: 6 }).map((_, idx) => (
        // Indexes are stable because the list length is constant; the
        // noUncheckedIndexedAccess-friendly cast below keeps types clean.
        <li key={(idx + 1).toString()}>
          <Card className="h-full border-border/60">
            <CardContent className="flex h-full flex-col gap-3">
              <div className="flex items-center gap-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-4 w-12 rounded-full" />
                <Skeleton className="ml-auto h-3 w-16" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <div className="flex gap-3">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-3 w-20" />
                </div>
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
