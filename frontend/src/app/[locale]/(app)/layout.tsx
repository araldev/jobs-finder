import { AppShell } from "@/components/layout/AppShell";
import { EmailVerificationBanner } from "@/components/auth/EmailVerificationBanner";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <EmailVerificationBanner />
      {children}
    </AppShell>
  );
}