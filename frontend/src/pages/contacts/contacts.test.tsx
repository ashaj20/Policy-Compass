import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as apiModule from "../../lib/api";
import { routeHref, validateDestination } from "../../lib/contacts";
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

const owner = {
  id: "c1",
  name: "Jane Smith",
  job_title: "Head of Repairs",
  email: "jane.smith@example.org",
  phone: "0300 123 4567",
  policy_count: 2,
};
const route = {
  id: "r1",
  label: "Repairs Helpdesk",
  route_type: "EMAIL",
  destination: "repairs@example.org",
  description: null,
  is_default: true,
  policy_count: 0,
};

describe("contact helpers", () => {
  it("builds the right link for each route type", () => {
    expect(routeHref({ route_type: "EMAIL", destination: "a@example.org" })).toBe("mailto:a@example.org");
    expect(routeHref({ route_type: "PHONE", destination: "0300 123 4567" })).toBe("tel:03001234567");
    expect(routeHref({ route_type: "WEBSITE", destination: "https://example.org" })).toBe("https://example.org");
  });

  it("checks the destination against the type", () => {
    expect(validateDestination("EMAIL", "nope")).toMatch(/valid email/);
    expect(validateDestination("PHONE", "abc")).toMatch(/valid phone/);
    expect(validateDestination("WEBSITE", "example.org/help")).toBeUndefined();
    expect(validateDestination("WEBSITE", "")).toBe("Enter the web address");
  });
});

describe("Contacts page", () => {
  it("shows internal owners and public routes as clearly separate sections", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [owner], help_routes: [route] } }),
    });
    renderApp("/internal/contacts");
    const internal = await screen.findByRole("region", { name: /Internal policy owners/ });
    expect(within(internal).getByText("Staff only. Never shown to the public.")).toBeInTheDocument();
    expect(within(internal).getByText("Jane Smith")).toBeInTheDocument();
    expect(within(internal).getByText("Used by 2 policies")).toBeInTheDocument();
    const pub = screen.getByRole("region", { name: /Public help routes/ });
    expect(within(pub).getByText("Shown to the public when an answer can't be found.")).toBeInTheDocument();
    expect(within(pub).getByRole("link", { name: "repairs@example.org" })).toHaveAttribute("href", "mailto:repairs@example.org");
    expect(within(pub).getByText("Default")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contacts" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the empty states from the design", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [], help_routes: [] } }),
    });
    renderApp("/internal/contacts");
    expect(await screen.findByText("No contacts configured")).toBeInTheDocument();
    expect(screen.getByText("No public help route configured")).toBeInTheDocument();
  });

  it("adds a policy owner", async () => {
    let sent: unknown;
    let owners: unknown[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners, help_routes: [] } }),
      "POST /organisations/o1/policy-owners": (body) => {
        sent = body;
        owners = [{ ...owner, policy_count: 0 }];
        return { status: 201, body: owner };
      },
    });
    renderApp("/internal/contacts");
    await userEvent.click(await screen.findByRole("button", { name: "+ Add contact" }));
    const dialog = screen.getByRole("dialog", { name: "Add policy owner" });
    expect(dialog).toHaveTextContent("Policy owners are never shown on public pages.");
    await userEvent.type(within(dialog).getByLabelText("Name"), "Jane Smith");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add contact" }));
    expect(within(dialog).getByText(/Enter an email address or phone number/)).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText("Email"), "jane.smith@example.org");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add contact" }));
    expect(await screen.findByText("Jane Smith has been added.")).toBeInTheDocument();
    expect(sent).toMatchObject({ name: "Jane Smith", email: "jane.smith@example.org" });
  });

  it("adds a help route with a destination that fits its type", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [], help_routes: [] } }),
      "POST /organisations/o1/help-routes": (body) => {
        sent = body;
        return { status: 201, body: { ...route, label: "Help Centre", route_type: "WEBSITE" } };
      },
    });
    renderApp("/internal/contacts");
    await userEvent.click(await screen.findByRole("button", { name: "+ Add route" }));
    const dialog = screen.getByRole("dialog", { name: "Add public help route" });
    await userEvent.selectOptions(within(dialog).getByLabelText("Type"), "WEBSITE");
    await userEvent.type(within(dialog).getByLabelText("Label"), "Help Centre");
    await userEvent.type(within(dialog).getByLabelText("Web address"), "example.org/help");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add route" }));
    expect(await screen.findByText("Help Centre has been added.")).toBeInTheDocument();
    expect(sent).toEqual({ label: "Help Centre", route_type: "WEBSITE", destination: "example.org/help", description: "" });
  });

  it("warns how many policies use a contact before removing it", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [owner], help_routes: [] } }),
      "DELETE /organisations/o1/policy-owners/c1": () => ({ status: 204 }),
    });
    renderApp("/internal/contacts");
    await userEvent.click(await screen.findByRole("button", { name: "Remove Jane Smith" }));
    const dialog = screen.getByRole("dialog", { name: "Remove Jane Smith?" });
    expect(dialog).toHaveTextContent('2 policies use this contact. They will show "Not assigned"');
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText("Jane Smith has been removed.")).toBeInTheDocument();
  });

  it("is read-only for staff", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [owner], help_routes: [route] } }),
    });
    renderApp("/internal/contacts");
    expect(await screen.findByText("Jane Smith")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
  });
});

describe("Choosing contacts for a policy", () => {
  it("offers owners and help routes on upload, depending on the audience", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies/categories": () => ({ status: 200, body: [] }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [owner], help_routes: [route] } }),
    });
    const upload = vi.spyOn(apiModule, "uploadWithProgress").mockRejectedValue(new apiModule.ApiError(500, "x", "stop"));
    renderApp("/internal/policies/new");
    await screen.findByRole("heading", { name: "Upload policy" });
    await userEvent.click(screen.getByRole("radio", { name: /Both/ }));
    await userEvent.selectOptions(await screen.findByLabelText("Internal policy owner"), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Public help route"), "r1");
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["%PDF"], "repairs.pdf", { type: "application/pdf" }));
    await userEvent.type(screen.getByLabelText("Version"), "1.0");
    await userEvent.type(screen.getByLabelText("Effective date"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Category"), "Repairs");
    await userEvent.click(screen.getByRole("button", { name: "Save & process" }));
    const body = upload.mock.calls[0][1] as FormData;
    expect(body.get("owner_id")).toBe("c1");
    expect(body.get("help_route_id")).toBe("r1");

    // Switching to Public hides the owner, and it isn't sent.
    await userEvent.click(screen.getByRole("radio", { name: /Public/ }));
    expect(screen.queryByLabelText("Internal policy owner")).not.toBeInTheDocument();
  });

  it("points to Contacts when none are set up yet", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies/categories": () => ({ status: 200, body: [] }),
      "GET /organisations/o1/contacts": () => ({ status: 200, body: { owners: [], help_routes: [] } }),
    });
    renderApp("/internal/policies/new");
    await screen.findByRole("heading", { name: "Upload policy" });
    await userEvent.click(screen.getByRole("radio", { name: /Internal/ }));
    expect(await screen.findByText(/No policy owners yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add one in Contacts" })).toHaveAttribute("href", "/internal/contacts");
  });
});
