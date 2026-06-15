import { PageTransition } from "@/components/layout/PageTransition";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsLoading() {
  return (
    <PageTransition>
      <Skeleton className="mb-6 h-8 w-48" />
      <div className="max-w-2xl space-y-6">
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    </PageTransition>
  );
}
