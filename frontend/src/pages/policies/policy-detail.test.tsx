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

const activeVersion = {
  id: "v1",
  version: "3.2",
  effective_date: "2026-09-01",
  status: "ACTIVE",
  original_filename: "Emergency Repairs Policy.pdf",
  file_size: 2048,
  uploaded_at: "2026-10-17T10:00:00Z",
  uploaded_by: "jane@example.org",
  submitted_at: "2026-10-17T11:00:00Z",
  submitted_by: "john@example.org",
  activated_at: "2026-10-17T12:00:00Z",
  activated_by: "jane@example.org",
};

const detail = {
  id: "p1",
  name: "Emergency Repairs Policy",
  category: "Repairs",
  audience: "INTERNAL",
  source: "Approved by the Board, August 2026",
  created_at: "2026-10-17T10:00:00Z",
  updated_at: "2026-10-17T10:00:00Z",
  status: "ACTIVE",
  version_count: 1,
  owner: null,
  help_route: null,
  archived_at: null as string | null,
  archived_by: null as string | null,
  latest_version: activeVersion,
  current_version: activeVersion,
  active_version_id: "v1" as string | null,
  versions: [activeVersion] as Record<string, unknown>[],
};
const BASE = "/organisations/o1/policies/p1";

describe("Policy detail", () => {
  it("shows status, audience, version, details, escalation and the document", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByRole("heading", { name: "Emergency Repairs Policy" })).toBeInTheDocument();
    expect(screen.getByText("Version 3.2", { selector: ".pc-version-meta span" })).toBeInTheDocument();
    expect(screen.getByText("Effective 01 September 2026")).toBeInTheDocument();
    expect(screen.getByText("Available to Policy Compass")).toBeInTheDocument();
    expect(screen.getByText("Approved by the Board, August 2026")).toBeInTheDocument();
    const escalation = screen.getByRole("region", { name: "Escalation" });
    expect(within(escalation).getByText("Policy owner")).toBeInTheDocument();
    // Internal-only policies have no public help route.
    expect(within(escalation).queryByText("Public help route")).not.toBeInTheDocument();
    const download = within(screen.getByRole("region", { name: "Document" })).getByRole("link", { name: /Download/ });
    expect(download).toHaveAttribute("href", `/api${BASE}/versions/v1/file`);
    expect(screen.getByRole("link", { name: "← Back to policies" })).toBeInTheDocument();
  });

  it("explains when a policy is still processing", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({
        status: 200,
        body: { ...detail, status: "PROCESSING", active_version_id: null, versions: [{ ...activeVersion, status: "PROCESSING" }] },
      }),
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByText("Processing. Not yet used to answer questions.")).toBeInTheDocument();
  });

  it("edits policy details", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
      [`PATCH ${BASE}`]: (body) => {
        sent = body;
        return { status: 200, body: { ...detail, name: "Emergency Repairs", category: "Maintenance" } };
      },
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit policy" }));
    const dialog = screen.getByRole("dialog", { name: "Edit policy" });
    const name = within(dialog).getByLabelText("Policy name");
    expect(name).toHaveFocus();
    await userEvent.clear(name);
    await userEvent.type(name, "Emergency Repairs");
    await userEvent.clear(within(dialog).getByLabelText("Category"));
    await userEvent.type(within(dialog).getByLabelText("Category"), "Maintenance");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Your changes have been saved.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Emergency Repairs" })).toBeInTheDocument();
    expect(sent).toEqual({
      name: "Emergency Repairs",
      category: "Maintenance",
      source: "Approved by the Board, August 2026",
      audience: "INTERNAL",
    });
  });

  it("warns before making an internal policy public", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit policy" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("radio", { name: /Public/ }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This policy will be used to answer public questions.");
  });

  it("shows a name clash on the name field", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
      [`PATCH ${BASE}`]: () => ({
        status: 409,
        body: {
          error: {
            code: "policy_exists",
            message: "Another policy already has this name",
            fields: { name: "Another policy already has this name" },
          },
        },
      }),
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit policy" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await within(dialog).findByText(/Another policy already has this name/)).toBeInTheDocument();
  });

  it("is read-only for staff", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByRole("heading", { name: "Emergency Repairs Policy" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit policy" })).not.toBeInTheDocument();
  });

  it("explains when a policy is no longer available", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({
        status: 404,
        body: { error: { code: "not_found", message: "This policy is no longer available." } },
      }),
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByRole("alert")).toHaveTextContent("This policy is no longer available.");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("is reached from the policy list", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": () => ({
        status: 200,
        body: {
          policies: [
            {
              id: "p1",
              name: "Emergency Repairs Policy",
              category: "Repairs",
              audience: "INTERNAL",
              status: "READY",
              version: "3.2",
              effective_date: "2026-09-01",
              updated_at: "2026-10-17T10:00:00Z",
              owner: null,
            },
          ],
          categories: ["Repairs"],
        },
      }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies");
    await userEvent.click(await screen.findByRole("link", { name: "Emergency Repairs Policy" }));
    expect(await screen.findByText("Available to Policy Compass")).toBeInTheDocument();
  });

  it("archives after confirmation", async () => {
    let archived = false;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
      [`POST ${BASE}/archive`]: () => {
        archived = true;
        return {
          status: 200,
          body: { ...detail, status: "ARCHIVED", archived_at: "2026-10-17T12:00:00Z", archived_by: "jane@example.org" },
        };
      },
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Archive policy" }));
    const dialog = screen.getByRole("dialog", { name: "Archive this policy?" });
    expect(dialog).toHaveTextContent("Archived policies will no longer be used to answer questions.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(archived).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Archive policy" }));

    expect(await screen.findByText("The policy has been archived.")).toBeInTheDocument();
    expect(screen.getByText("This policy is archived and is no longer used to answer questions.")).toBeInTheDocument();
    expect(screen.getByText(/^Archived .* by jane@example.org\.$/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive policy" })).not.toBeInTheDocument();
  });

  it("restores an archived policy", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({
        status: 200,
        body: { ...detail, status: "ARCHIVED", archived_at: "2026-10-17T12:00:00Z", archived_by: "jane@example.org" },
      }),
      [`POST ${BASE}/restore`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Restore policy" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Restore this policy?" })).getByRole("button", { name: "Restore policy" }));
    expect(await screen.findByText("The policy has been restored.")).toBeInTheDocument();
    expect(screen.getByText("Available to Policy Compass")).toBeInTheDocument();
  });

  it("shows no archive controls to staff", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      [`GET ${BASE}`]: () => ({ status: 200, body: detail }),
    });
    renderApp("/internal/policies/p1");
    await screen.findByRole("heading", { name: "Emergency Repairs Policy" });
    expect(screen.queryByRole("button", { name: "Archive policy" })).not.toBeInTheDocument();
  });
});