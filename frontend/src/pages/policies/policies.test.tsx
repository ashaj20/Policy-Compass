import { screen, waitFor, within } from "@testing-library/react";
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

const item = (overrides: Record<string, unknown>) => ({
  id: "p1",
  name: "Emergency Repairs Policy",
  category: "Repairs",
  audience: "INTERNAL",
  status: "READY",
  version: "3.2",
  effective_date: "2026-09-01",
  updated_at: "2026-10-17T10:00:00Z",
  owner: null,
  ...overrides,
});

const list = {
  policies: [
    item({}),
    item({ id: "p2", name: "Complaints Policy", category: "Complaints", audience: "PUBLIC", version: "2.1" }),
    item({ id: "p3", name: "Tenancy Policy", category: "Tenancy", audience: "BOTH", status: "PROCESSING", version: "4.0" }),
  ],
  categories: ["Complaints", "Repairs", "Tenancy"],
};

describe("Policies list", () => {
  it("shows policies with audience, version, status, effective date and owner", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": () => ({ status: 200, body: list }),
    });
    renderApp("/internal/policies");
    const row = (await screen.findByText("Emergency Repairs Policy")).closest("tr")!;
    expect(within(row).getByText("Internal")).toBeInTheDocument();
    expect(within(row).getByText("3.2")).toBeInTheDocument();
    expect(within(row).getByText("Ready")).toBeInTheDocument();
    expect(within(row).getByText("01 September 2026")).toBeInTheDocument();
    expect(within(row).getByText("Not assigned")).toBeInTheDocument();
    const tenancy = screen.getByText("Tenancy Policy").closest("tr")!;
    expect(within(tenancy).getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("3 policies")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Upload policy" })).toHaveAttribute("href", "/internal/policies/new");
  });

  it("filters by audience, status and category through the API", async () => {
    const urls: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": (_, url) => {
        urls.push(url.search);
        return { status: 200, body: list };
      },
    });
    renderApp("/internal/policies");
    await screen.findByText("Emergency Repairs Policy");
    await userEvent.selectOptions(screen.getByLabelText("Audience"), "PUBLIC");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "READY");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "Complaints");
    await waitFor(() => expect(urls[urls.length - 1]).toBe("?audience=PUBLIC&status=READY&category=Complaints"));
  });

  it("searches after typing stops", async () => {
    const urls: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": (_, url) => {
        urls.push(url.search);
        return { status: 200, body: list };
      },
    });
    renderApp("/internal/policies");
    await screen.findByText("Emergency Repairs Policy");
    await userEvent.type(screen.getByLabelText("Search policies"), "repairs");
    await waitFor(() => expect(urls[urls.length - 1]).toBe("?q=repairs"));
  });

  it("offers to clear filters when nothing matches", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": (_, url) => ({
        status: 200,
        body: url.search ? { policies: [], categories: list.categories } : list,
      }),
    });
    renderApp("/internal/policies?audience=BOTH&status=FAILED");
    expect(await screen.findByText("No policies match these filters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("Emergency Repairs Policy")).toBeInTheDocument();
  });

  it("shows an upload prompt when an admin has no policies", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": () => ({ status: 200, body: { policies: [], categories: [] } }),
    });
    renderApp("/internal/policies");
    expect(await screen.findByText("No policies yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload policy" })).toHaveAttribute("href", "/internal/policies/new");
  });

  it("shows a friendly error with retry", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": () => ({ status: 500, body: { error: { code: "internal_error", message: "x" } } }),
    });
    renderApp("/internal/policies");
    expect(await screen.findByText("We couldn't load your policies. Please try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("is read-only for staff: no upload button and no status filter", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/policies": () => ({ status: 200, body: { policies: [item({})], categories: ["Repairs"] } }),
    });
    renderApp("/internal/policies");
    expect(await screen.findByText("Emergency Repairs Policy")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Upload policy/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Policies" })).toHaveAttribute("aria-current", "page");
  });
});
