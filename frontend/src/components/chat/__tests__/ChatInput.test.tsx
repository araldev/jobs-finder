import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "../ChatInput";

describe("ChatInput", () => {
  it("renders input and send button", () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);

    expect(
      screen.getByPlaceholderText("Describe the job you're looking for..."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("calls onSend with input value when send button is clicked", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<ChatInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(
      "Describe the job you're looking for...",
    );
    await user.type(input, "remote react jobs");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onSend).toHaveBeenCalledWith("remote react jobs");
  });

  it("calls onSend when Enter is pressed", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<ChatInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(
      "Describe the job you're looking for...",
    );
    await user.type(input, "senior engineer");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenCalledWith("senior engineer");
  });

  it("does not call onSend for empty input", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<ChatInput onSend={onSend} disabled={false} />);

    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables input and button when disabled is true", () => {
    render(<ChatInput onSend={vi.fn()} disabled={true} />);

    expect(
      screen.getByPlaceholderText("Describe the job you're looking for..."),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("clears input after sending", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<ChatInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(
      "Describe the job you're looking for...",
    );
    await user.type(input, "test query");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(input).toHaveValue("");
  });
});
