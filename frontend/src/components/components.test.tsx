import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Alert, Button, ErrorState, Input, LoadingState } from ".";
import { AudienceBadge } from "./AudienceBadge";

describe("Input", () => {
  it("is labelled and links its error for screen readers", () => {
    render(<Input label="Email" error="Enter a valid email address" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy)).toHaveTextContent("Enter a valid email address");
  });
});

describe("Button", () => {
  it("is disabled and busy while loading", () => {
    render(<Button loading>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("Alert", () => {
  it("announces errors assertively and info politely", () => {
    render(
      <>
        <Alert tone="error" title="Failed" />
        <Alert tone="info" title="Note" />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
    expect(screen.getByRole("status")).toHaveTextContent("Note");
  });
});

describe("States", () => {
  it("loading state is a live status region", () => {
    render(<LoadingState label="Searching approved policies..." />);
    expect(screen.getByRole("status")).toHaveTextContent("Searching approved policies...");
  });

  it("error state offers retry and back actions with a reference", async () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        message="We couldn't load your policies. Please try again."
        errorId="abc123"
        onRetry={onRetry}
        onBack={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Go back" })).toBeInTheDocument();
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
  });
});

describe("AudienceBadge", () => {
  it("names the audience in text, not just colour", () => {
    render(
      <>
        <AudienceBadge audience="INTERNAL" />
        <AudienceBadge audience="PUBLIC" />
        <AudienceBadge audience="BOTH" />
      </>,
    );
    expect(screen.getByText("Internal")).toBeInTheDocument();
    expect(screen.getByText("Public")).toBeInTheDocument();
    expect(screen.getByText("Both")).toBeInTheDocument();
    expect(screen.getByText(/audience: staff only/)).toBeInTheDocument();
  });
});