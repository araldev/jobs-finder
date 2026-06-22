"use client";

import { useTranslations } from "next-intl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { GlobalSignoutButton } from "./GlobalSignoutButton";
import { DeleteAccountDialog } from "./DeleteAccountDialog";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function AccountSection() {
  const supabase = createClient();
  const t = useTranslations("Settings.account");
  const tCommon = useTranslations("Common");
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void supabase.auth.getUser().then(({ data }) => {
      if (active) setUserEmail(data.user?.email ?? null);
    });
    return () => {
      active = false;
    };
  }, [supabase]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-lg">{t("title")}</CardTitle>
        <CardDescription>
          {t("changePassword")} · {t("signOut")} · {t("deleteAccount")}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <ChangePasswordForm />
        <Separator />
        <GlobalSignoutButton />
        <Separator />
        <div
          className="rounded-xl border border-destructive/40 p-6"
          data-testid="delete-account-destructive-card"
        >
          {userEmail ? (
            <DeleteAccountDialog userEmail={userEmail} />
          ) : (
            <p className="text-sm text-muted-foreground">{tCommon("loading")}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}