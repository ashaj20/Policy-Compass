import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const staff = { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] };

const dashboard = {
  counts: { total: 5, active: 1, awaiting_approval: 1, drafts_to_review: 1, processing: 1, failed: 1, archived: 1 },
  attention: [
    { kind: "failed", policy_id: "p5", policy_name: "Failed Policy", version: "1.0", since: "2026-10-17T10:00:00Z" },
    { kind: "awaiting_approval", policy_id: "p2", policy_name: "Awaiting Policy", version: "2.0", since: "2026-10-17T10:00:00Z" },
  ],
  setup: [
    { key: "organisation", done: true },
    { key: "policy", done: true },
    { key: "owner", done: false },
    { key: "help_route", done: false },
    { key: "branding", done: true },
  ],
};

describe("Dashboard", () => {
  it("shows policy counts, what needs attention, setup steps and recent activity", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/dashboard": () => ({ status: 200, body: dashboard }),
      "GET /organisations/o1/audit-events": () => ({
        status: 200,
        body: {
          events: [
            {
              id: "e1",
              timestamp: "2026-10-17T10:00:00Z",
              actor: "jane@example.org",
              action: "POLICY_UPLOADED",
              object_type: "policy",
              object_id: "p1",
              object_label: "Rent Policy",
              previous: null,
              new: { version: "1.4" },
            },
          ],
          next_before: null,
        },
      }),
    });
    renderApp("/internal");
    const summary = await screen.findByRole("region", { name: "Policy summary" });
    expect(within(summary).getByRole("link", { name: /1\s*Active policies/ })).toHaveAttribute("href", "/internal/policies?status=ACTIVE");
    expect(within(summary).getByRole("link", { name: /1\s*Failed/ })).toHaveAttribute("href", "/internal/policies?status=FAILED");

    const attention = screen.getByRole("region", { name: "Needs attention" });
    expect(within(attention).getByRole("link", { name: "Failed Policy" })).toHaveAttribute("href", "/internal/policies/p5");
    expect(attention).toHaveTextContent("Awaiting Policy version 2.0 is ready for approval");

    const setup = screen.getByRole("region", { name: "Let's get your knowledge base ready" });
    expect(within(setup).getByRole("link", { name: "Add a policy owner for staff escalation" })).toHaveAttribute("href", "/internal/contacts");
    expect(setup).toHaveTextContent("Organisation created (done)");

    expect(await screen.findByText(/uploaded the policy Rent Policy/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });

  it("hides the checklist once setup is complete", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/dashboard": () => ({
        status: 200,
        body: { ...dashboard, setup: dashboard.setup.map((s) => ({ ...s, done: true })) },
      }),
      "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
    });
    renderApp("/internal");
    await screen.findByRole("region", { name: "Policy summary" });
    expect(screen.queryByRole("region", { name: "Let's get your knowledge base ready" })).not.toBeInTheDocument();
  });

  it("shows staff only what they can act on", async () => {
    const spy = mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/dashboard": () => ({
        status: 200,
        body: {
          counts: { total: 2, active: 1, awaiting_approval: 0, drafts_to_review: 1, processing: 0, failed: 0, archived: 0 },
          attention: [{ kind: "draft", policy_id: "p3", policy_name: "Draft Policy", version: "1.0", since: "2026-10-17T10:00:00Z" }],
          setup: [],
        },
      }),
    });
    renderApp("/internal");
    const summary = await screen.findByRole("region", { name: "Policy summary" });
    expect(within(summary).queryByText("Failed")).not.toBeInTheDocument();
    expect(within(summary).queryByText("Awaiting approval")).not.toBeInTheDocument();
    expect(screen.getByText(/needs reviewing and marking ready/)).toBeInTheDocument();
    expect(spy.mock.calls.some(([url]) => String(url).includes("audit-events"))).toBe(false);
  });

  it("says when nothing needs attention", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/dashboard": () => ({ status: 200, body: { ...dashboard, attention: [] } }),
      "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
    });
    renderApp("/internal");
    expect(await screen.findByText("Nothing needs your attention right now.")).toBeInTheDocument();
  });
});