"use client";

import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { LogOut, Settings } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";

/**
 * `scope` controls the Supabase `signOut({ scope })` argument:
 *   - `'local'` (DEFAULT, unchanged): revoke only this tab's session.
 *   - `'global'`: revoke every session in the project for this user.
 *
 * The header chip keeps `scope: 'local'` by default (existing UX).
 * Settings callers can pass `scope="global"` to opt into the
 * "sign out everywhere" behavior (REQ-AUTH-019 / REQ-AUTH-020).
 *
 * REQ-PDPRSC-004 refactor (commit 5): auth state is read from the
 * shared `useCurrentUser` hook instead of calling
 * `supabase.auth.getSession()` directly + subscribing to
 * `onAuthStateChange`. The hook owns the subscription lifecycle
 * (mounted on hook mount, invalidated on every auth event, cleaned
 * up on unmount). One `/auth/v1/user` fetch per 5min cache window,
 * shared with `EmailVerificationBanner`.
 */
export interface AuthStatusProps {
  scope?: "local" | "global";
}

export function AuthStatus({ scope = "local" }: AuthStatusProps) {
  const supabase = createClient();
  const router = useRouter();
  const t = useTranslations("Navigation");
  const tc = useTranslations("Common");
  const { data: user, isLoading } = useCurrentUser();

  const email = user?.email ?? null;

  async function logout() {
    if (scope === "global") {
      await supabase.auth.signOut({ scope: "global" });
    } else {
      await supabase.auth.signOut();
    }
    router.push("/login");
    router.refresh();
  }

  if (isLoading) return null;

  if (email) {
    const initials = email.charAt(0).toUpperCase();

    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 rounded-full"
            aria-label={tc("userMenu")}
          >
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-xs font-medium">
                {initials}
              </AvatarFallback>
            </Avatar>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={8}>
          <DropdownMenuLabel className="font-normal">
            <div className="flex flex-col">
              <span className="text-sm font-medium">{email}</span>
              <span className="text-xs text-muted-foreground">
                {tc("signedInAs")}
              </span>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link href="/settings" className="flex items-center gap-2">
              <Settings className="h-4 w-4" />
              {t("settings.label")}
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={logout}
            className="text-destructive focus:text-destructive"
          >
            <LogOut className="h-4 w-4" />
            {tc("signOut")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <Link href="/login">
      <Button variant="outline" size="sm">
        {tc("signIn")}
      </Button>
    </Link>
  );
}
