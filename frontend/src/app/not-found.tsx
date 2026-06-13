import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center py-16 text-center">
      <h2 className="font-display text-xl font-bold">Page not found</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        The page you are looking for does not exist
      </p>
      <Button variant="outline" className="mt-4" asChild>
        <Link href="/">Back to Dashboard</Link>
      </Button>
    </div>
  );
}
