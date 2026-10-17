import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { describeEvent, type AuditEvent } from "../../lib/audit";
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

function event(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    id: crypto.randomUUID(),
    timestamp: "2026-10-17T14:05:00Z",
    actor: "jane@example.org",
    action: "ORGANISATION_CREATED",
    object_type: "organisation",
    object_id: "o1",
    object_label: "Riverside Housing",
    previous: null,
    new: null,
    ...overrides,
  };
}

describe("describeEvent", () => {
  it("describes each kind of change in plain English", () => {
    expect(describeEvent(event({})).summary).toBe("created the organisation Riverside Housing");
    expect(
      describeEvent(event({ action: "MEMBER_INVITED", object_label: "john@example.org", new: { role: "ADMIN" } })).summary,
    ).toBe("invited john@example.org as an administrator");
    expect(describeEvent(event({ action: "MEMBER_JOINED", new: { role: "STAFF" } })).summary).toBe(
      "joined as a staff member",
    );
    const roleChange = describeEvent(
      event({ action: "MEMBER_ROLE_CHANGED", object_label: "john@example.org", previous: { role: "STAFF" }, new: { role: "ADMIN" } }),
    );
    expect(roleChange.changes).toEqual([{ label: "Role", from: "Staff member", to: "Administrator" }]);
    const url = describeEvent(
      event({ action: "PUBLIC_URL_CHANGED", previous: { slug: "old-url" }, new: { slug: "new-url" } }),
    );
    expect(url.changes).toEqual([{ label: "Public URL", from: "/p/old-url", to: "/p/new-url" }]);
    const settings = describeEvent(
      event({ action: "ORGANISATION_SETTINGS_CHANGED", previous: { website: null }, new: { website: "https://x.org" } }),
    );
    expect(settings.changes).toEqual([{ label: "Website", from: "Not set", to: "https://x.org" }]);
  });
});

describe("Activity page", () => {
  it("shows who did what and when, newest first", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/audit-events": () => ({
        status: 200,
        body: {
          events: [
            event({ action: "ORGANISATION_SETTINGS_CHANGED", previous: { name: "Riverside" }, new: { name: "Riverside Housing" } }),
            event({}),
          ],
          next_before: null,
        },
      }),
    });
    renderApp("/internal/settings/activity");
    const list = await screen.findByRole("list", { name: "Activity, newest first" });
    const items = within(list).getAllByRole("listitem").filter((li) => li.classList.contains("pc-audit__event"));
    expect(items[0]).toHaveTextContent("jane@example.org changed the organisation details");
    expect(items[0]).toHaveTextContent("Name: Riverside → changed to Riverside Housing");
    expect(items[1]).toHaveTextContent("created the organisation Riverside Housing");
    expect(items[0].querySelector("time")).toHaveAttribute("datetime", "2026-10-17T14:05:00Z");
    expect(screen.getByText(/Entries can't be edited or deleted/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete|edit/i })).not.toBeInTheDocument();
  });

  it("loads older activity on request", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/audit-events": (_, url) =>
        url.searchParams.get("before")
          ? { status: 200, body: { events: [event({ action: "LOGO_REMOVED" })], next_before: null } }
          : { status: 200, body: { events: [event({ action: "LOGO_UPDATED" })], next_before: "cursor1" } },
    });
    renderApp("/internal/settings/activity");
    expect(await screen.findByText(/uploaded a new logo/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show older activity" }));
    expect(await screen.findByText(/removed the logo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show older activity" })).not.toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/audit-events": () => ({ status: 200, body: { events: [], next_before: null } }),
    });
    renderApp("/internal/settings/activity");
    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
  });

  it("is admin-only and hidden from staff navigation", async () => {
    const spy = mockApi({ "GET /auth/me": () => ({ status: 200, body: staff }) });
    renderApp("/internal/settings/activity");
    expect(await screen.findByText("You don't have permission to view activity.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Activity" })).not.toBeInTheDocument();
    expect(spy.mock.calls.some(([url]) => String(url).includes("audit-events"))).toBe(false);
  });
});
