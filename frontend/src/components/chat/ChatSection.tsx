/**
 * Chat section — T-008 replaces this with the full chat UI
 * (ChatPanel, ChatMessage, ChatInput, ChatStreamBanner,
 * NoChatAvailable, useChatStream). The placeholder keeps the
 * build green and shows a hint of what is coming.
 */
export function ChatSection(): React.ReactElement {
  return (
    <div className="rounded-2xl border border-dashed border-border/60 bg-card/40 p-6 text-sm text-muted-foreground">
      Chat section — full UI lands in T-008.
    </div>
  );
}
