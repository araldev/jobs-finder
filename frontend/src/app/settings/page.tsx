import { PageTransition } from "@/components/layout/PageTransition";
import { PlatformConfigCard } from "@/components/settings/PlatformConfigCard";
import { NotificationSettings } from "@/components/settings/NotificationSettings";

export default function SettingsPage() {
  return (
    <PageTransition>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure your dashboard preferences
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        <PlatformConfigCard />
        <NotificationSettings />
      </div>
    </PageTransition>
  );
}
