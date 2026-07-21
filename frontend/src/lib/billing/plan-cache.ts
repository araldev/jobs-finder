import type { Subscription } from "@/types/billing";

interface CachedEntry {
  subscription: Subscription;
  expiresAt: number;
}

const PLAN_CACHE_TTL_MS = 60_000;

const _cache = new Map<string, CachedEntry>();

export function planCacheGet(userId: string): Subscription | null {
  const entry = _cache.get(userId);
  if (!entry) return null;
  if (Date.now() > entry.expiresAt) {
    _cache.delete(userId);
    return null;
  }
  return entry.subscription;
}

export function planCacheSet(userId: string, subscription: Subscription): void {
  _cache.set(userId, {
    subscription,
    expiresAt: Date.now() + PLAN_CACHE_TTL_MS,
  });
}

export function planCacheInvalidate(userId: string): void {
  _cache.delete(userId);
}

export function planCacheClear(): void {
  _cache.clear();
}
