import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessages } from "../ChatMessages";
import type { ChatMessage } from "@/types/chat";

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
      <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
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
      <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
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
      <ChatMessages messages={messages} status="streaming" openedJobIds={new Set()} />,
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
      <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
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
      <ChatMessages messages={messages} status="done" openedJobIds={new Set()} />,
    );

    expect(screen.getByText("Found matches:")).toBeInTheDocument();
    expect(
      screen.getByText(/Frontend Developer/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Acme/)).toBeInTheDocument();
  });

  it("renders error message", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "test" },
      {
        id: "2",
        role: "assistant",
        content: "",
        error: {
          code: "llm_unavailable",
          message: "The AI assistant is currently unavailable.",
        },
      },
    ];

    render(
      <ChatMessages messages={messages} status="error" openedJobIds={new Set()} />,
    );

    expect(
      screen.getByText("The AI assistant is currently unavailable."),
    ).toBeInTheDocument();
  });

  it("shows empty state when no messages", () => {
    render(<ChatMessages messages={[]} status="idle" openedJobIds={new Set()} />);

    expect(
      screen.getByText(
        /Describe the job you are looking for in natural language/i,
      ),
    ).toBeInTheDocument();
  });
});
