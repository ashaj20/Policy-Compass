import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../test/utils";

afterEach(() => vi.restoreAllMocks());

const admin = {
  id: "u1",
  email: "jane@example.org",
  memberships: [{ organisation_id: "o1", organisation_name: "Riverside Housing", organisation_slug: "riverside-housing", role: "ADMIN" }],
};

const allClear = {
  days: 7,
  processing_failures: 0,
  unanswered: 0,
  service_unavailable: 0,
  limit_reached: 0,
  answers_today: 3,
  daily_answer_limit: 100,
  negative_feedback: [],
};

function dashboardWith(ops: object) {
  return mockApi({
    "GET /auth/me": () => ({ status: 200, body: admin }),
    "GET /organisations/o1/dashboard": () => ({
      status: 200,
      body: {
        counts: { total: 1, active: 1, awaiting_approval: 0, drafts_to_review: 0, processing: 0, failed: 0, archived: 0 },
        attention: [],
        setup: [],
        questions: { total: 0, internal: 0, public: 0, answered: 0, unanswered: 0, open_gaps: 0 },
      },
    }),
    "GET /organisations/o1/operational-status": () => ({ status: 200, body: ops }),
    "GET /organisations/o1/policy-usage": () => ({ status: 200, body: { days: 30, policies: [] } }),
    "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
    "GET /organisations/o1/questions": () => ({ status: 200, body: { questions: [], next_before: null } }),
  });
}

describe("Operational status (US-035A)", () => {
  it("says when everything is fine", async () => {
    dashboardWith(allClear);
    renderApp("/internal");
    const card = await screen.findByRole("region", { name: "Operational status" });
    expect(card).toHaveTextContent("No problems in the last 7 days.");
    expect(card).toHaveTextContent("No unanswered questions in the last 7 days · 3 of 100 answers used today");
  });

  it("lists problems in plain language with links", async () => {
    dashboardWith({
      ...allClear,
      processing_failures: 1,
      unanswered: 4,
      service_unavailable: 2,
      limit_reached: 1,
      answers_today: 85,
      negative_feedback: [{ policy_id: "p1", name: "Repairs Policy", unhelpful: 3 }],
    });
    renderApp("/internal");
    const card = await screen.findByRole("region", { name: "Operational status" });
    expect(within(card).getByRole("link", { name: "1 policy upload couldn't be processed" })).toHaveAttribute(
      "href",
      "/internal/policies?status=FAILED",
    );
    expect(card).toHaveTextContent("2 questions couldn't be answered because the answering service was unavailable");
    expect(card).toHaveTextContent("1 question went unanswered because the daily answer limit was reached");
    expect(
      within(card).getByRole("link", { name: "3 answers using Repairs Policy marked unhelpful in the last 30 days" }),
    ).toHaveAttribute("href", "/internal/questions?scope=all&feedback=unhelpful&policy_id=p1");
    expect(within(card).getByRole("link", { name: "4 unanswered questions in the last 7 days" })).toBeInTheDocument();
    expect(within(card).getByText("85 of 100 answers used today")).toHaveClass("pc-ops__warn");
  });

  it("the negative feedback link shows those answers and can be cleared", async () => {
    const searches: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/questions": (_b, url) => {
        searches.push(url.search);
        return { status: 200, body: { questions: [], next_before: null } };
      },
    });
    renderApp("/internal/questions?scope=all&feedback=unhelpful&policy_id=p1");
    expect(await screen.findByText(/Showing answers marked unhelpful that used one policy/)).toBeInTheDocument();
    const first = new URLSearchParams(searches[0]);
    expect(first.get("feedback")).toBe("unhelpful");
    expect(first.get("policy_id")).toBe("p1");
    await userEvent.click(screen.getByRole("button", { name: "Show all questions" }));
    await vi.waitFor(() => expect(searches[searches.length - 1]).toBe("?scope=all"));
  });
});
