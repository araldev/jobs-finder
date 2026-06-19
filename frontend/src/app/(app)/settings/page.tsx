import { PageTransition } from "@/components/layout/PageTransition";
import { PlatformConfigCard } from "@/components/settings/PlatformConfigCard";
import { NotificationSettings } from "@/components/settings/NotificationSettings";
import { UserCVCard } from "@/components/settings/UserCVCard";

export default function SettingsPage() {
  return (
    <PageTransition>
      <div className="max-w-2xl space-y-6">
        <UserCVCard />
        <PlatformConfigCard />
        <NotificationSettings />
      </div>
    </PageTransition>
  );
}
