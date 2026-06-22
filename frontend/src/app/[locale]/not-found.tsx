import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/ui/button";

export default async function NotFound() {
  const t = await getTranslations("Errors.notFoundPage");

  return (
    <div className="flex h-full flex-col items-center justify-center py-16 text-center">
      <h2 className="font-display text-xl font-bold">{t("title")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t("description")}</p>
      <Button variant="outline" className="mt-4" asChild>
        <Link href="/">{t("home")}</Link>
      </Button>
    </div>
  );
}