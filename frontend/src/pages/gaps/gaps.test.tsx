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
const now = new Date().toISOString();

const gap = {
  id: "g1",
  question: "Can tenants keep pets in supported housing?",
  audience: "PUBLIC",
  asked_at: now,
  status: "OPEN",
  updated_at: now,
  question_id: "q1",
  searched_policies: [{ id: "p1", name: "Tenancy Policy", archived: false }],
  notes: null,
  resolution: null,
  created_at: now,
  closed_at: null,
};

describe("Knowledge gaps (US-033A)", () => {
  it("lists gaps with status counts and filters by status", async () => {
    const searches: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/knowledge-gaps": (_b, url) => {
        searches.push(url.search);
        return { status: 200, body: { gaps: [gap], counts: { OPEN: 1, INVESTIGATING: 2, RESOLVED: 0, CLOSED: 3 } } };
      },
    });
    renderApp("/internal/knowledge-gaps");
    const link = await screen.findByRole("link", { name: gap.question });
    expect(link).toHaveAttribute("href", "/internal/knowledge-gaps/g1");
    expect(link.closest("li")).toHaveTextContent("Open");
    expect(link.closest("li")).toHaveTextContent("Asked by the public");
    const filters = screen.getByRole("navigation", { name: "Filter by status" });
    expect(within(filters).getByRole("button", { name: "All 6" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(filters).getByRole("button", { name: "Investigating 2" }));
    await vi.waitFor(() => expect(searches[searches.length - 1]).toBe("?status=INVESTIGATING"));
    expect(screen.getByRole("link", { name: "Knowledge gaps" })).toHaveAttribute("aria-current", "page");
  });

  it("updates status and notes, and requires a resolution to resolve", async () => {
    const sent: unknown[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/knowledge-gaps/g1": () => ({ status: 200, body: gap }),
      "PATCH /organisations/o1/knowledge-gaps/g1": (body) => {
        sent.push(body);
        return { status: 200, body: { ...gap, ...(body as object) } };
      },
    });
    renderApp("/internal/knowledge-gaps/g1");
    expect(await screen.findByText(gap.question)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tenancy Policy" })).toHaveAttribute("href", "/internal/policies/p1");
    expect(screen.getByRole("link", { name: "See what Policy Compass said" })).toHaveAttribute("href", "/internal/questions/q1");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "RESOLVED");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Describe how this gap was resolved")).toBeInTheDocument();
    expect(sent).toEqual([]);

    await userEvent.type(screen.getByLabelText("Notes"), "Checked with the housing team");
    await userEvent.type(screen.getByLabelText("Resolution"), "Added a pets section to the Tenancy Policy");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Knowledge gap updated.")).toBeInTheDocument();
    expect(sent).toEqual([
      { status: "RESOLVED", notes: "Checked with the housing team", resolution: "Added a pets section to the Tenancy Policy" },
    ]);
  });

  it("an unanswered question can be tracked as a gap", async () => {
    const created: unknown[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/questions/q1": () => ({
        status: 200,
        body: {
          id: "q1",
          question: gap.question,
          status: "INSUFFICIENT_EVIDENCE",
          reason: "no_evidence",
          answer: null,
          citations: [],
          escalation: null,
          feedback: null,
          audience: "PUBLIC",
          asked_by_me: false,
          knowledge_gap_id: null,
          asked_at: now,
        },
      }),
      "POST /organisations/o1/knowledge-gaps": (body) => {
        created.push(body);
        return { status: 201, body: gap };
      },
      "GET /organisations/o1/knowledge-gaps/g1": () => ({ status: 200, body: gap }),
    });
    renderApp("/internal/questions/q1");
    await userEvent.click(await screen.findByRole("button", { name: "Track as knowledge gap" }));
    expect(await screen.findByRole("heading", { name: "Knowledge gap", level: 1 })).toBeInTheDocument();
    expect(created).toEqual([{ question_id: "q1" }]);
  });

  it("staff can't see knowledge gaps", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: staff }) });
    renderApp("/internal/knowledge-gaps");
    expect(await screen.findByText("You don't have permission to view knowledge gaps.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Knowledge gaps" })).not.toBeInTheDocument();
  });
});
