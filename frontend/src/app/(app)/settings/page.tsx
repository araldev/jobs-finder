import { PageTransition } from "@/components/layout/PageTransition";
import { PlatformConfigCard } from "@/components/settings/PlatformConfigCard";
import { NotificationSettings } from "@/components/settings/NotificationSettings";
import { UserCVCard } from "@/components/settings/UserCVCard";
import { AccountSection } from "@/components/settings/AccountSection";

export default function SettingsPage() {
  return (
    <PageTransition>
      <div className="max-w-2xl space-y-6">
        <UserCVCard />
        <PlatformConfigCard />
        <NotificationSettings />
        <AccountSection />
      </div>
    </PageTransition>
  );
}
