"use client";

import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { usePlatformConfig } from "@/hooks/usePlatformConfig";
import { SOURCES } from "@/types/job";

export function PlatformConfigCard() {
  const { enabledSources, toggleSource, isEnabled } = usePlatformConfig();

  const handleSave = () => {
    // The hook auto-persists to localStorage — this button confirms it's active
    toast.success(`Showing ${enabledSources.length} of ${SOURCES.length} platforms`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-lg">Active Platforms</CardTitle>
        <CardDescription>
          Choose which job platforms to display. Changes apply immediately to the dashboard and search.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {SOURCES.map((source) => (
          <div key={source} className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium capitalize">{source}</p>
              <p className="text-xs text-muted-foreground">
                {isEnabled(source) ? "Active" : "Disabled"}
              </p>
            </div>
            <Switch
              checked={isEnabled(source)}
              onCheckedChange={() => toggleSource(source)}
            />
          </div>
        ))}
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
