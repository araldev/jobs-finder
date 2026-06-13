"use client";

import { useState } from "react";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";

export function NotificationSettings() {
  const [enabled, setEnabled] = useState(false);

  const handleSave = () => {
    toast.success("Notification settings saved (local only)");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-lg">Notifications</CardTitle>
        <CardDescription>
          Configure alerts for new job listings. (Coming soon)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Enable Notifications</p>
            <p className="text-xs text-muted-foreground">
              Receive alerts when new jobs are found
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
          />
        </div>
        <button
          onClick={handleSave}
          className="mt-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Save Preferences
        </button>
      </CardContent>
    </Card>
  );
}
