import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Answer } from "../lib/questions";
import { InsufficientEvidenceCard } from "./InsufficientEvidenceCard";

const base: Answer = {
  id: "q1",
  question: "Can I get my boiler serviced?",
  status: "INSUFFICIENT_EVIDENCE",
  reason: "no_evidence",
  answer: null,
  citations: [],
  escalation: null,
  asked_at: "2026-10-18T10:00:00Z",
};

describe("InsufficientEvidenceCard (public)", () => {
  it("shows the public help route", () => {
    render(
      <InsufficientEvidenceCard
        audience="public"
        answer={{
          ...base,
          escalation: { kind: "help_route", label: "Repairs Helpdesk", route_type: "WEBSITE", destination: "https://help.example.org", description: null },
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "We couldn't find enough information in our approved policies to answer this." })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Need help?" })).toHaveTextContent("Repairs Helpdesk");
    expect(screen.getByRole("link", { name: "Visit Help Centre" })).toHaveAttribute("href", "https://help.example.org");
  });

  it("uses the generic message when no route exists", () => {
    render(<InsufficientEvidenceCard audience="public" answer={base} />);
    expect(screen.getByText("Please contact the organisation through its main customer support channel.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("never shows a policy owner on the public card", () => {
    render(
      <InsufficientEvidenceCard
        audience="public"
        answer={{
          ...base,
          escalation: { kind: "owner", name: "Sam Patel", job_title: null, email: "sam@example.org", phone: null, policy_name: "Repairs Policy" },
        }}
      />,
    );
    expect(screen.queryByText(/Sam Patel/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sam@example.org/)).not.toBeInTheDocument();
  });
});
