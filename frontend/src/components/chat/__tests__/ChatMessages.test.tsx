import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessages } from "../ChatMessages";
import { renderWithIntl } from "@/test-utils";
import type { ChatMessage } from "@/types/chat";
import esMessages from "@/messages/es.json";
import enMessages from "@/messages/en.json";

const mockJobs = [
  {
    id: "1",
    source: "linkedin" as const,
    title: "Frontend Developer",
    company: "Acme",
    location: "Madrid",
    url: "https://example.com/job/1",
    posted_at: "2026-06-01T00:00:00Z",
    description: null,
  },
];

describe("ChatMessages", () => {
  it("renders user message", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "remote jobs" },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(screen.getByText("remote jobs")).toBeInTheDocument();
  });

  it("renders assistant message", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "Here are some jobs for you.",
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(
      screen.getByText("Here are some jobs for you."),
    ).toBeInTheDocument();
  });

  it("shows thinking indicator during streaming", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "",
        extractedQuery: "react",
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="streaming" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    // The OpenCode-style three-dot thinking animation appears
    // in the "Looking for:" row while the LLM is processing.
    expect(screen.getByTestId("thinking-dots")).toBeInTheDocument();
  });

  it("hides thinking indicator when done", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      { id: "2", role: "assistant", content: "Done" },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(
      screen.queryByTestId("thinking-dots"),
    ).not.toBeInTheDocument();
  });

  it("renders job matches in assistant message", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "Found matches:",
        jobs: mockJobs,
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(screen.getByText("Found matches:")).toBeInTheDocument();
    expect(
      screen.getByText(/Frontend Developer/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Acme/)).toBeInTheDocument();
  });

  it("renders translated error message by code (ES locale)", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "",
        // `generic` is one of the Chat.errors.* keys (F3 contract).
        // AssistantMessage renders t(Chat.errors.code) when the code
        // resolves; for an unknown code it falls back to `message`.
        error: {
          code: "generic",
          message: "ignored-because-key-matches",
        },
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="error" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(
      screen.getByText(esMessages.Chat.errors.generic),
    ).toBeInTheDocument();
  });

  it("renders translated error message by code (EN locale)", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "",
        error: {
          code: "generic",
          message: "ignored-because-key-matches",
        },
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="error" openedJobIds={new Set()} />,
        { locale: "en" },
      ),
    );

    expect(
      screen.getByText(enMessages.Chat.errors.generic),
    ).toBeInTheDocument();
  });

  it("falls back to raw server message when error code has no translation key", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "",
        error: {
          // Unknown code → AssistantMessage falls back to `message`.
          code: "llm_unavailable",
          message: "The AI assistant is currently unavailable.",
        },
      },
    ];

    render(
      renderWithIntl(
        <ChatMessages messages={messages} status="error" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    expect(
      screen.getByText("The AI assistant is currently unavailable."),
    ).toBeInTheDocument();
  });

  it("shows empty state when no messages", () => {
    render(
      renderWithIntl(
        <ChatMessages messages={[]} status="idle" openedJobIds={new Set()} />,
        { locale: "es" },
      ),
    );

    // NOTE: ChatMessages.tsx has a hardcoded EN empty-state string.
    // It is intentionally out of scope for this cycle — it is F3-
    // adjacent (chat component), but the explore's F3 scope is the 3
    // useChat error literals only. The assertion matches the live text.
    expect(
      screen.getByText(
        /Describe the job you are looking for in natural language/i,
      ),
    ).toBeInTheDocument();
  });
});
