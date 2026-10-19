import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const staff = { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] };

const summary = (id: string, question: string, extra = {}) => ({
  id,
  question,
  status: "ANSWERED",
  reason: null,
  sources: [],
  helpful: null,
  audience: "INTERNAL",
  asked_at: new Date().toISOString(),
  ...extra,
});

describe("Question history for administrators (US-032, US-033)", () => {
  it("shows everyone's questions with audience, and filters to unanswered public questions", async () => {
    const searches: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/questions": (_body, url) => {
        searches.push(url.search);
        return {
          status: 200,
          body: {
            questions: [
              summary("q1", "Can tenants keep pets?", { status: "INSUFFICIENT_EVIDENCE", audience: "PUBLIC" }),
              summary("q2", "How quickly are emergency repairs attended?", { sources: ["Repairs Policy"] }),
            ],
            next_before: null,
          },
        };
      },
    });
    renderApp("/internal/questions");
    expect(await screen.findByRole("heading", { name: "Questions", level: 1 })).toBeInTheDocument();
    const pets = (await screen.findByRole("link", { name: "Can tenants keep pets?" })).closest("li")!;
    expect(pets).toHaveTextContent("Not enough information");
    expect(pets).toHaveTextContent("Asked by the public");
    expect(screen.getByRole("link", { name: "How quickly are emergency repairs attended?" }).closest("li")).toHaveTextContent(
      "Asked by staff",
    );
    expect(searches[0]).toBe("?scope=all");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "INSUFFICIENT_EVIDENCE");
    await userEvent.selectOptions(screen.getByLabelText("Audience"), "PUBLIC");
    await vi.waitFor(() => {
      const last = new URLSearchParams(searches[searches.length - 1]);
      expect(last.get("scope")).toBe("all");
      expect(last.get("status")).toBe("INSUFFICIENT_EVIDENCE");
      expect(last.get("audience")).toBe("PUBLIC");
    });

    await userEvent.selectOptions(screen.getByLabelText("Show"), "mine");
    expect(await screen.findByRole("heading", { name: "My questions", level: 1 })).toBeInTheDocument();
    expect(screen.queryByLabelText("Audience")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(new URLSearchParams(searches[searches.length - 1]).get("scope")).toBeNull());
  });

  it("staff only ever see their own questions, and are told admins can see questions", async () => {
    const searches: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions": (_body, url) => {
        searches.push(url.search);
        return { status: 200, body: { questions: [], next_before: null } };
      },
    });
    renderApp("/internal/questions?scope=all&audience=PUBLIC");
    expect(await screen.findByRole("heading", { name: "My questions", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/Administrators can see questions asked in your organisation, but not who asked them/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Show")).not.toBeInTheDocument();
    expect(searches.every((s) => !s.includes("scope=all") && !s.includes("audience"))).toBe(true);
  });

  it("an administrator viewing someone else's answer sees their feedback but can't give it", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/questions/q2": () => ({
        status: 200,
        body: {
          id: "q2",
          question: "How quickly are emergency repairs attended?",
          status: "ANSWERED",
          reason: null,
          answer: "Within 24 hours.",
          citations: [],
          escalation: null,
          feedback: { helpful: false, reason: "UNCLEAR" },
          audience: "INTERNAL",
          asked_by_me: false,
          asked_at: new Date().toISOString(),
        },
      }),
    });
    renderApp("/internal/questions/q2");
    expect(await screen.findByText("The person who asked marked this answer unhelpful.")).toBeInTheDocument();
    expect(screen.queryByText("Was this answer helpful?")).not.toBeInTheDocument();
    expect(screen.getByText(/Asked by staff, today/)).toBeInTheDocument();
    expect(screen.getByText("Question", { selector: ".pc-answer__kicker" })).toBeInTheDocument();
  });

  it("shows a public question's help route, not the staff wording", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/questions/q1": () => ({
        status: 200,
        body: {
          id: "q1",
          question: "Can tenants keep pets?",
          status: "INSUFFICIENT_EVIDENCE",
          reason: "no_evidence",
          answer: null,
          citations: [],
          escalation: { kind: "help_route", label: "Customer Services", route_type: "EMAIL", destination: "help@example.org", description: null },
          feedback: null,
          audience: "PUBLIC",
          asked_by_me: false,
          asked_at: new Date().toISOString(),
        },
      }),
    });
    renderApp("/internal/questions/q1");
    const help = await screen.findByRole("region", { name: "Need help?" });
    expect(within(help).getByText("Customer Services")).toBeInTheDocument();
  });
});

describe("Dashboard question metrics (US-031)", () => {
  it("shows this week's questions and unanswered questions to administrators", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/dashboard": () => ({
        status: 200,
        body: {
          counts: { total: 2, active: 2, awaiting_approval: 0, drafts_to_review: 0, processing: 0, failed: 0, archived: 0 },
          attention: [],
          setup: [],
          questions: { total: 12, internal: 9, public: 3, answered: 10, unanswered: 2 },
        },
      }),
      "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
      "GET /organisations/o1/questions": () => ({ status: 200, body: { questions: [], next_before: null } }),
    });
    renderApp("/internal");
    const summaryRegion = await screen.findByRole("region", { name: "Policy summary" });
    const total = within(summaryRegion).getByRole("link", { name: /12\s*Questions this week/ });
    expect(total).toHaveTextContent("9 staff · 3 public");
    expect(total.getAttribute("href")).toMatch(/^\/internal\/questions\?scope=all&from=\d{4}-\d{2}-\d{2}$/);
    const unanswered = within(summaryRegion).getByRole("link", { name: /2\s*Unanswered this week/ });
    expect(unanswered.getAttribute("href")).toContain("status=INSUFFICIENT_EVIDENCE");
  });
});
