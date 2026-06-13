import { formatDistanceToNow, format, isToday, isYesterday } from "date-fns";

export function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (isToday(date)) return formatDistanceToNow(date, { addSuffix: true });
  if (isYesterday(date)) return "Yesterday";
  return format(date, "MMM d, yyyy");
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

export function getPlatformColorClass(platform: string): string {
  const map: Record<string, string> = {
    linkedin: "bg-[hsl(var(--linkedin))]",
    indeed: "bg-[hsl(var(--indeed))]",
    infojobs: "bg-[hsl(var(--infojobs))]",
  };
  return map[platform.toLowerCase()] ?? "bg-muted";
}
