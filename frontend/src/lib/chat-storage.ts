/**
 * Shared localStorage utilities for chat state persistence.
 * Used by useChat hook (ChatPanel), job detail page (to mark jobs as opened),
 * and any component that needs to show "opened" badges on job cards.
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";

export const CHAT_STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.chat;

export interface ChatStorage {
  messages: unknown[];
  openedJobIds: string[];
}

function _loadStorage(): ChatStorage {
  if (typeof window === "undefined") return { messages: [], openedJobIds: [] };
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return { messages: [], openedJobIds: [] };
    const parsed = JSON.parse(raw) as ChatStorage;
    // Ensure openedJobIds is always an array (backward compat with old seenJobIds data)
    return {
      messages: parsed.messages ?? [],
      openedJobIds: Array.isArray(parsed.openedJobIds) ? parsed.openedJobIds : [],
    };
  } catch {
    return { messages: [], openedJobIds: [] };
  }
}

function _saveStorage(storage: ChatStorage): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(storage));
  } catch {
    // localStorage unavailable or quota exceeded — ignore
  }
}

/** Load full chat storage (messages + openedJobIds). */
export function loadChatStorage(): ChatStorage {
  return _loadStorage();
}

/** Save full chat storage (messages + openedJobIds). */
export function saveChatStorage(storage: ChatStorage): void {
  _saveStorage(storage);
}

/** Mark a job as opened (user visited its detail page). */
export function markJobAsOpened(jobId: string): void {
  const storage = _loadStorage();
  if (!storage.openedJobIds.includes(jobId)) {
    storage.openedJobIds.push(jobId);
    _saveStorage(storage);
  }
}

/** Get all job IDs that have been marked as opened. */
export function getOpenedJobIds(): string[] {
  return _loadStorage().openedJobIds;
}

/** Clear the entire chat storage (messages + openedJobIds). */
export function clearChatStorage(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(CHAT_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * React hook to subscribe to opened job IDs.
 * Returns the set of job IDs that have been marked as opened.
 * Components can use this to show a "Abierta" badge on job cards.
 */
export function useOpenedJobs(): Set<string> {
  const [openedJobIds, setOpenedJobIds] = useState<Set<string>>(() => new Set(getOpenedJobIds()));

  useEffect(() => {
    // Sync with storage on mount (handles updates from other tabs/pages)
    const storage = _loadStorage();
    setOpenedJobIds(new Set(storage.openedJobIds));

    // Poll for storage changes from other tabs
    const interval = setInterval(() => {
      const current = _loadStorage();
      setOpenedJobIds((prev) => {
        const newIds = current.openedJobIds;
        if (newIds.length !== prev.size) return new Set(newIds);
        for (const id of newIds) {
          if (!prev.has(id)) return new Set(newIds);
        }
        return prev;
      });
    }, 500);

    return () => clearInterval(interval);
  }, []);

  return openedJobIds;
}
