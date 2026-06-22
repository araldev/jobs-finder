import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchBar } from "../SearchBar";
import { renderWithIntl } from "@/test-utils";

describe("SearchBar", () => {
  it("renders with placeholder", () => {
    render(renderWithIntl(<SearchBar value="" onChange={() => {}} />, { locale: "es" }));
    expect(screen.getByPlaceholderText(/buscar/i)).toBeInTheDocument();
  });

  it("calls onChange when typing", () => {
    const onChange = vi.fn();
    render(renderWithIntl(<SearchBar value="" onChange={onChange} />, { locale: "es" }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "test" } });
    expect(onChange).toHaveBeenCalledWith("test");
  });

  it("shows clear button when value exists", () => {
    render(renderWithIntl(<SearchBar value="test" onChange={() => {}} />, { locale: "es" }));
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("does not show clear button when value is empty", () => {
    render(renderWithIntl(<SearchBar value="" onChange={() => {}} />, { locale: "es" }));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onChange with empty string on clear", () => {
    const onChange = vi.fn();
    render(renderWithIntl(<SearchBar value="test" onChange={onChange} />, { locale: "es" }));
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("");
  });
});