import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as apiModule from "../../lib/api";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const john = { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] };
const sarah = { id: "u3", email: "sarah@example.org", memberships: [membership("STAFF")] };

const BASE = "/organisations/o1/policies/p1";

const version = (overrides: Record<string, unknown>) => ({
  id: "v1",
  version: "1.0",
  effective_date: "2026-01-01",
  status: "ACTIVE",
  original_filename: "repairs-v1.pdf",
  file_size: 2048,
  uploaded_at: "2026-01-01T10:00:00Z",
  uploaded_by: "jane@example.org",
  activated_at: "2026-01-02T10:00:00Z",
  activated_by: "jane@example.org",
  ...overrides,
});

const v1 = version({});
function policyWith(pending: Record<string, unknown> | null, active = true) {
  const versions = [...(pending ? [version({ id: "v2", version: "2.0", activated_at: null, activated_by: null, ...pending })] : []), ...(active ? [v1] : [])];
  return {
    id: "p1",
    name: "Emergency Repairs Policy",
    category: "Repairs",
    audience: "INTERNAL",
    source: null,
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-10-17T10:00:00Z",
    status: active ? "ACTIVE" : String(pending?.status),
    version_count: versions.length,
    owner: null,
    help_route: null,
    archived_at: null,
    archived_by: null,
    latest_version: versions[0],
    current_version: active ? v1 : versions[0],
    active_version_id: active ? "v1" : null,
    versions,
  };
}

describe("Version review and approval", () => {
  it("lets a staff member mark a draft ready, without approval controls", async () => {
    let marked = false;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: john }),
      [`GET ${BASE}`]: () => ({ status: 200, body: policyWith({ status: "DRAFT" }) }),
      [`POST ${BASE}/versions/v2/mark-ready`]: () => {
        marked = true;
        return { status: 200, body: policyWith({ status: "READY", submitted_by: "john@example.org", submitted_at: "2026-10-17T11:00:00Z" }) };
      },
    });
    renderApp("/internal/policies/p1");
    const history = await screen.findByRole("list", { name: "Versions, newest first" });
    expect(screen.getByText(/Version 2.0 stays out of use until it is approved/)).toBeInTheDocument();
    await userEvent.click(within(history).getByRole("button", { name: "Mark ready for approval" }));
    expect(await screen.findByText("Version 2.0 is ready for an administrator's approval.")).toBeInTheDocument();
    expect(marked).toBe(true);
    expect(screen.getByText("Ready – awaiting approval")).toBeInTheDocument();
    expect(screen.getByText(/Marked ready .* by john@example.org/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve & activate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload new version" })).not.toBeInTheDocument();
  });

  it("only offers withdraw to the person who marked it ready", async () => {
    const readyBy = { status: "READY", submitted_by: "john@example.org", submitted_at: "2026-10-17T11:00:00Z" };
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: sarah }),
      [`GET ${BASE}`]: () => ({ status: 200, body: policyWith(readyBy) }),
    });
    renderApp("/internal/policies/p1");
    await screen.findByRole("list", { name: "Versions, newest first" });
    expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
  });

  it("asks an administrator to confirm approval, naming the version it replaces", async () => {
    let activated = false;
    const ready = { status: "READY", submitted_by: "john@example.org", submitted_at: "2026-10-17T11:00:00Z" };
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: policyWith(ready) }),
      [`POST ${BASE}/versions/v2/activate`]: () => {
        activated = true;
        return { status: 200, body: policyWith(null) };
      },
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Approve & activate" }));
    const dialog = screen.getByRole("dialog", { name: "Approve and activate version 2.0?" });
    expect(dialog).toHaveTextContent("Version 1.0 will be marked Superseded and kept for history.");
    expect(dialog).toHaveTextContent("Your name and the time are recorded with this approval.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(activated).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve & activate" }));
    expect(await screen.findByText("Version 2.0 is now active.")).toBeInTheDocument();
    expect(activated).toBe(true);
  });

  it("requires a reason to send a version back", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: policyWith({ status: "READY", submitted_by: "john@example.org" }) }),
      [`POST ${BASE}/versions/v2/reject`]: (body) => {
        sent = body;
        return { status: 200, body: policyWith({ status: "DRAFT", rejection_reason: "Section 4 is out of date", rejected_by: "jane@example.org" }) };
      },
    });
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Send back" }));
    const dialog = screen.getByRole("dialog", { name: "Send back version 2.0?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send back to draft" }));
    expect(within(dialog).getByText(/Say why this version is being sent back/)).toBeInTheDocument();
    expect(sent).toBeUndefined();

    await userEvent.type(within(dialog).getByLabelText("Reason"), "Section 4 is out of date");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send back to draft" }));
    expect(await screen.findByText("Version 2.0 has been sent back to draft.")).toBeInTheDocument();
    expect(sent).toEqual({ reason: "Section 4 is out of date" });
    expect(screen.getByText("Sent back by an administrator")).toBeInTheDocument();
    expect(screen.getByText(/Section 4 is out of date/)).toBeInTheDocument();
  });

  it("explains that a failed version will never replace the active one", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({
        status: 200,
        body: policyWith({
          status: "FAILED",
          failure_reason: "We couldn't find enough text in this document.",
          error_id: null,
        }),
      }),
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByText(/will never replace the active version/)).toBeInTheDocument();
    expect(screen.getByText("We couldn't process this version")).toBeInTheDocument();
    expect(screen.getByText("We couldn't find enough text in this document.")).toBeInTheDocument();
    expect(screen.getByText(/Your original document has not been deleted/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark ready for approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve & activate" })).not.toBeInTheDocument();
    expect(screen.getByText("Available to Policy Compass")).toBeInTheDocument();
  });

  it("uploads a new version from the policy page", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({ status: 200, body: policyWith(null) }),
    });
    const upload = vi
      .spyOn(apiModule, "uploadWithProgress")
      .mockResolvedValue(policyWith({ status: "PROCESSING" }) as never);
    renderApp("/internal/policies/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Upload new version" }));
    const dialog = screen.getByRole("dialog", { name: "Upload new version" });
    expect(dialog).toHaveTextContent("The current active version stays in use");
    const input = dialog.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["%PDF"], "repairs-v2.pdf", { type: "application/pdf" }));
    await userEvent.type(within(dialog).getByLabelText("Version"), "2.0");
    await userEvent.type(within(dialog).getByLabelText("Effective date"), "2026-09-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload & process" }));

    expect(await screen.findByText("Version 2.0 uploaded. It is being processed.")).toBeInTheDocument();
    const [path, body] = upload.mock.calls[0] as unknown as [string, FormData];
    expect(path).toBe(`${BASE}/versions`);
    expect(body.get("version")).toBe("2.0");
    expect(body.get("effective_date")).toBe("2026-09-01");
  });
});
