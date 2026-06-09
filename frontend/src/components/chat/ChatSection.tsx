"use client";

import { ChatPanel } from "./ChatPanel";

/**
 * Right-side chat section. The actual UI lives in ChatPanel
 * (glass surface, message list, stream banner, input). The
 * wrapper exists so the page can render a single element and so
 * we have a place to add chat-only layout decisions later
 * (e.g. mobile bottom-sheet) without touching the page.
 */
export function ChatSection(): React.ReactElement {
  return <ChatPanel />;
}
