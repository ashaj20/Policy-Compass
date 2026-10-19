import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../test/utils";

afterEach(() => vi.restoreAllMocks());

const admin = {
  id: "u1",
  email: "jane@example.org",
  memberships: [{ organisation_id: "o1", organisation_name: "Riverside Housing", organisation_slug: "riverside-housing", role: "ADMIN" }],
};
const now = new Date().toISOString();
const usage = {
  days: 30,
  policies: [
    { policy_id: "p1", name: "Repairs Policy", active: true, questions: 43, last_used: now },
    { policy_id: "p2", name: "Complaints Policy", active: true, questions: 1, last_used: now },
    { policy_id: "p3", name: "Pets Policy", active: true, questions: 0, last_used: null },
    { policy_id: "p4", name: "Draft Policy", active: false, questions: 0, last_used: null },
  ],
};

describe("Policy usage (US-034)", () => {
  it("shows the most used policies and active ones nobody has used", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/dashboard": () => ({
        status: 200,
        body: {
          counts: { total: 4, active: 3, awaiting_approval: 0, drafts_to_review: 1, processing: 0, failed: 0, archived: 0 },
          attention: [],
          setup: [],
          questions: { total: 0, internal: 0, public: 0, answered: 0, unanswered: 0, open_gaps: 0 },
        },
      }),
      "GET /organisations/o1/policy-usage": () => ({ status: 200, body: usage }),
      "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
      "GET /organisations/o1/questions": () => ({ status: 200, body: { questions: [], next_before: null } }),
    });
    renderApp("/internal");
    const card = await screen.findByRole("region", { name: "Most used policies" });
    const items = within(card).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Repairs Policy43 questions · last used today");
    expect(items[1]).toHaveTextContent("Complaints Policy1 question");
    expect(within(card).getByRole("link", { name: "Repairs Policy" })).toHaveAttribute("href", "/internal/policies/p1");
    expect(card).toHaveTextContent("Not used yet: Pets Policy.");
    expect(card).not.toHaveTextContent("Draft Policy");
  });
});
