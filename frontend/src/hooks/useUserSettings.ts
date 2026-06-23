"use client";

import { useCallback, useEffect, useState } from "react";
import type { UserSettings } from "@/types/user";

const DEFAULT_SETTINGS: UserSettings = {
  enabled_platforms: ["linkedin", "indeed", "infojobs"],
  notifications_enabled: true,
} as const;

export interface UseUserSettingsReturn {
  settings: UserSettings | null;
  isLoading: boolean;
  error: string | null;
  updateSettings: (settings: Partial<UserSettings>) => Promise<void>;
}

async function fetchSettings(): Promise<UserSettings> {
  const res = await fetch("/api/users/me/settings");
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Unauthorized");
    }
    throw new Error("Failed to fetch settings");
  }
  return res.json();
}

async function updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
  const res = await fetch("/api/users/me/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Unauthorized");
    }
    throw new Error("Failed to update settings");
  }
  return res.json();
}

export function useUserSettings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSettings() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchSettings();
        setSettings(data);
      } catch {
        // If API fails, use defaults
        setSettings(DEFAULT_SETTINGS);
      } finally {
        setIsLoading(false);
      }
    }
    loadSettings();
  }, []);

  const updateSettingsFn = useCallback(async (newSettings: Partial<UserSettings>) => {
    setError(null);
    try {
      const updated = await updateSettings(newSettings);
      setSettings(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update settings");
    }
  }, []);

  return {
    settings,
    isLoading,
    error,
    updateSettings: updateSettingsFn,
  };
}
