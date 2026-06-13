import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Briefcase } from "lucide-react";
import { StatCard } from "../StatCard";

describe("StatCard", () => {
  it("renders label and value", () => {
    render(<StatCard icon={Briefcase} label="Total Jobs" value={42} />);
    expect(screen.getByText("Total Jobs")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders trend when provided", () => {
    render(
      <StatCard
        icon={Briefcase}
        label="Total Jobs"
        value={42}
        trend={{ value: 12, isUp: true }}
      />,
    );
    expect(screen.getByText("▲ 12%")).toBeInTheDocument();
  });

  it("renders negative trend", () => {
    render(
      <StatCard
        icon={Briefcase}
        label="Total Jobs"
        value={42}
        trend={{ value: 5, isUp: false }}
      />,
    );
    expect(screen.getByText("▼ 5%")).toBeInTheDocument();
  });
});
