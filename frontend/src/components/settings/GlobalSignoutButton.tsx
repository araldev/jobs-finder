"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { LogOut, Info } from "lucide-react";

import { createClient } from "@/lib/supabase/client";

/**
 * GlobalSignoutButton — REQ-AUTH-019.
 */
export function GlobalSignoutButton() {
  const supabase = createClient();
  const router = useRouter();
  const t = useTranslations("Auth.globalSignOut");

  async function handleSignOut() {
    const { error } = await supabase.auth.signOut({ scope: "global" });

    if (error) {
      toast.error(t("errorToast"));
      return;
    }

    router.push("/");
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-display text-base font-semibold">
        {t("confirmTitle")}
      </h3>
      <div className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <p>{t("tooltip")}</p>
      </div>
      <div>
        <button
          type="button"
          onClick={handleSignOut}
          className="inline-flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground transition-opacity hover:opacity-90"
        >
          <LogOut className="h-4 w-4" data-icon="inline-start" aria-hidden="true" />
          {t("triggerLabel")}
        </button>
      </div>
    </div>
  );
}