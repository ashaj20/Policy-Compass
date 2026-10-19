import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const staff = {
  id: "u2",
  email: "john@example.org",
  memberships: [
    { organisation_id: "o1", organisation_name: "Riverside Housing", organisation_slug: "riverside-housing", role: "STAFF" },
  ],
};

const dashboard = {
  counts: { total: 2, active: 2, awaiting_approval: 0, drafts_to_review: 0, processing: 0, failed: 0, archived: 0 },
  attention: [],
  setup: [],
};

const answered = {
  id: "q1",
  question: "How quickly should emergency repairs be dealt with?",
  status: "ANSWERED",
  reason: null,
  answer: "Emergency repairs are attended within 24 hours of a report.",
  citations: [
    {
      policy_id: "p1",
      policy_name: "Repairs Policy",
      version_id: "v1",
      version_label: "3.2",
      effective_date: "2026-09-01",
      section: "Emergency repairs",
      page: null,
      excerpt: "Emergency repairs such as gas leaks are attended within 24 hours of a report.",
    },
  ],
  escalation: null,
  feedback: null,
  asked_at: new Date().toISOString(),
};

const unanswered = {
  ...answered,
  id: "q2",
  question: "Who pays for boiler servicing?",
  status: "INSUFFICIENT_EVIDENCE",
  reason: "not_supported",
  answer: null,
  citations: [],
  escalation: {
    kind: "owner",
    name: "Sam Patel",
    job_title: "Head of Repairs",
    email: "sam@example.org",
    phone: null,
    policy_name: "Repairs Policy",
  },
};

describe("Internal question experience (US-025)", () => {
  it("dashboard → ask → answer with source → unanswered → policy owner", async () => {
    const replies = [answered, unanswered];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/dashboard": () => ({ status: 200, body: dashboard }),
      "GET /organisations/o1/questions": () => ({
        status: 200,
        body: {
          questions: [
            { id: "q0", question: "What is our complaints process?", status: "ANSWERED", reason: null, sources: [], helpful: null, asked_at: new Date().toISOString() },
          ],
          next_before: null,
        },
      }),
      "POST /organisations/o1/questions": () => ({ status: 201, body: replies.shift() }),
      "PUT /organisations/o1/questions/q1/feedback": (body) => ({ status: 200, body }),
    });
    renderApp("/internal");

    // Dashboard: recent questions and the ask box.
    const recent = await screen.findByRole("link", { name: "What is our complaints process?" });
    expect(recent).toHaveAttribute("href", "/internal/questions/q0");
    await userEvent.type(screen.getByLabelText("Ask a policy question"), "How quickly should emergency repairs be dealt with?{Enter}");

    // Answer with a source the member can inspect, then feedback.
    const answer = await screen.findByRole("region", { name: "Answer" });
    expect(answer).toHaveTextContent("within 24 hours");
    const sources = screen.getByRole("region", { name: "Sources" });
    await userEvent.click(within(sources).getByRole("button", { name: /Repairs Policy/ }));
    expect(within(sources).getByText(/gas leaks/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("Thanks for your feedback.")).toBeInTheDocument();

    // Unanswered: the policy owner is shown.
    await userEvent.click(screen.getByRole("button", { name: "Ask another question" }));
    await userEvent.type(screen.getByLabelText("What would you like to know?"), "Who pays for boiler servicing?{Enter}");
    const owner = await screen.findByRole("region", { name: "Policy owner" });
    expect(owner).toHaveTextContent("Sam Patel");
    expect(within(owner).getByRole("link", { name: "Contact policy owner" })).toBeInTheDocument();
  });
});
