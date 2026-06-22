import { AppShell } from "@/components/layout/AppShell";
import { EmailVerificationBanner } from "@/components/auth/EmailVerificationBanner";
import { Providers } from "@/app/providers";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell>
        <EmailVerificationBanner />
        {children}
      </AppShell>
    </Providers>
  );
}
