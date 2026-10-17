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

const jane = { id: "m1", user_id: "u1", email: "jane@example.org", role: "ADMIN", joined_at: "2026-10-01T10:00:00Z", is_you: true };
const john = { id: "m2", user_id: "u2", email: "john@example.org", role: "STAFF", joined_at: "2026-10-02T10:00:00Z", is_you: false };
const invitation = {
  id: "i1",
  email: "sarah@example.org",
  role: "STAFF",
  invited_at: "2026-10-10T10:00:00Z",
  expires_at: "2099-10-17T10:00:00Z",
  invited_by: "jane@example.org",
};

describe("Members page", () => {
  it("lists members and pending invitations", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane, john], invitations: [invitation] } }),
    });
    renderApp("/internal/settings/members");
    const members = await screen.findByRole("region", { name: "Members (2)" });
    expect(within(members).getByText("jane@example.org")).toBeInTheDocument();
    expect(within(members).getByText("You")).toBeInTheDocument();
    expect(within(members).getByLabelText("Role for john@example.org")).toHaveValue("STAFF");
    const pending = screen.getByRole("region", { name: "Pending invitations (1)" });
    expect(within(pending).getByText("sarah@example.org")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Members" })).toHaveAttribute("aria-current", "page");
  });

  it("invites a member through the Add member dialog", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane], invitations: [] } }),
      "POST /organisations/o1/invitations": (body) => {
        sent = body;
        return { status: 201, body: { ...invitation, email: "sarah@example.org", role: "ADMIN" } };
      },
    });
    renderApp("/internal/settings/members");
    await userEvent.click(await screen.findByRole("button", { name: "Add member" }));
    const dialog = screen.getByRole("dialog", { name: "Add member" });
    expect(within(dialog).getByLabelText("Email")).toHaveFocus();
    await userEvent.type(within(dialog).getByLabelText("Email"), "sarah@example.org");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "ADMIN");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));

    expect(await screen.findByText("We've sent an invitation to sarah@example.org.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sent).toEqual({ email: "sarah@example.org", role: "ADMIN" });
  });

  it("shows a duplicate membership error in the dialog", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane], invitations: [] } }),
      "POST /organisations/o1/invitations": () => ({
        status: 409,
        body: {
          error: {
            code: "already_member",
            message: "This person is already a member of your organisation",
            fields: { email: "This person is already a member of your organisation" },
          },
        },
      }),
    });
    renderApp("/internal/settings/members");
    await userEvent.click(await screen.findByRole("button", { name: "Add member" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Email"), "jane@example.org");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    expect(await within(dialog).findByText(/already a member/)).toBeInTheDocument();
  });

  it("closes the dialog with Escape and returns focus", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane], invitations: [] } }),
    });
    renderApp("/internal/settings/members");
    const opener = await screen.findByRole("button", { name: "Add member" });
    await userEvent.click(opener);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("asks for confirmation before removing a member", async () => {
    let removed = false;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({
        status: 200,
        body: { members: removed ? [jane] : [jane, john], invitations: [] },
      }),
      "DELETE /organisations/o1/members/m2": () => {
        removed = true;
        return { status: 204 };
      },
    });
    renderApp("/internal/settings/members");
    await userEvent.click(await screen.findByRole("button", { name: "Remove john@example.org" }));
    const dialog = screen.getByRole("dialog", { name: "Remove this member?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove member" }));

    expect(await screen.findByText("john@example.org has been removed.")).toBeInTheDocument();
    expect(removed).toBe(true);
    await waitFor(() => expect(screen.getByRole("region", { name: "Members (1)" })).toBeInTheDocument());
  });

  it("explains why the last administrator can't be removed", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane], invitations: [] } }),
      "DELETE /organisations/o1/members/m1": () => ({
        status: 409,
        body: { error: { code: "last_admin", message: "An organisation must have at least one administrator." } },
      }),
    });
    renderApp("/internal/settings/members");
    await userEvent.click(await screen.findByRole("button", { name: "Remove jane@example.org" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove member" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least one administrator");
  });

  it("changes a member's role", async () => {
    let patched: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/members": () => ({ status: 200, body: { members: [jane, john], invitations: [] } }),
      "PATCH /organisations/o1/members/m2": (body) => {
        patched = body;
        return { status: 200, body: { ...john, role: "ADMIN" } };
      },
    });
    renderApp("/internal/settings/members");
    await userEvent.selectOptions(await screen.findByLabelText("Role for john@example.org"), "ADMIN");
    expect(await screen.findByText("john@example.org is now administrator.")).toBeInTheDocument();
    expect(patched).toEqual({ role: "ADMIN" });
  });

  it("is not available to staff, and staff don't see it in the navigation", async () => {
    const spy = mockApi({ "GET /auth/me": () => ({ status: 200, body: staff }) });
    renderApp("/internal/settings/members");
    expect(await screen.findByText("You don't have permission to manage members.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
    expect(spy.mock.calls.some(([url]) => String(url).includes("/members"))).toBe(false);
  });
});

describe("Invitation page", () => {
  const details = { organisation_name: "Riverside Housing", email: "sarah@example.org", role: "STAFF", account_exists: false };
  const signedOut = { status: 401, body: { error: { code: "not_authenticated", message: "x" } } };

  it("lets a new person create an account and join", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => signedOut,
      "POST /invitations/lookup": () => ({ status: 200, body: details }),
      "POST /invitations/accept-new": (body) => {
        sent = body;
        return { status: 200, body: { id: "u3", email: "sarah@example.org", memberships: [membership("STAFF")] } };
      },
    });
    renderApp("/invite?token=tok");
    expect(await screen.findByText(/a staff member/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Password"), "a good long passphrase");
    await userEvent.type(screen.getByLabelText("Confirm password"), "a good long passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Create account and join" }));

    expect(await screen.findByRole("heading", { name: "Riverside Housing" })).toBeInTheDocument();
    expect(sent).toMatchObject({ token: "tok" });
  });

  it("asks an existing account holder to sign in, returning to the invitation", async () => {
    mockApi({
      "GET /auth/me": () => signedOut,
      "POST /invitations/lookup": () => ({ status: 200, body: { ...details, account_exists: true } }),
    });
    renderApp("/invite?token=tok");
    const link = await screen.findByRole("link", { name: "Sign in to accept" });
    expect(link).toHaveAttribute("href", `/login?next=${encodeURIComponent("/invite?token=tok")}`);
  });

  it("accepts in one click when signed in as the invited person", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: { id: "u3", email: "sarah@example.org", memberships: [] } }),
      "POST /invitations/lookup": () => ({ status: 200, body: { ...details, account_exists: true } }),
      "POST /invitations/accept": () => ({
        status: 200,
        body: { id: "u3", email: "sarah@example.org", memberships: [membership("STAFF")] },
      }),
    });
    renderApp("/invite?token=tok");
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByRole("heading", { name: "Riverside Housing" })).toBeInTheDocument();
  });

  it("warns when signed in as a different person", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: { id: "u9", email: "mark@example.org", memberships: [] } }),
      "POST /invitations/lookup": () => ({ status: 200, body: details }),
    });
    renderApp("/invite?token=tok");
    expect(await screen.findByRole("alert")).toHaveTextContent("This invitation was sent to sarah@example.org.");
  });

  it("explains an expired invitation", async () => {
    mockApi({
      "GET /auth/me": () => signedOut,
      "POST /invitations/lookup": () => ({
        status: 400,
        body: { error: { code: "invalid_invitation", message: "This invitation is invalid or has expired. Ask your administrator to send a new one." } },
      }),
    });
    renderApp("/invite?token=old");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
  });
});
