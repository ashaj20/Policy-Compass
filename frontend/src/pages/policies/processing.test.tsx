import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProcessingSteps } from "../../components/ProcessingSteps";
import * as apiModule from "../../lib/api";
import { polling } from "../../lib/polling";
import { mockApi, renderApp } from "../../test/utils";

beforeEach(() => {
  polling.intervalMs = 20;
});
afterEach(() => {
  polling.intervalMs = 2500;
  vi.restoreAllMocks();
});

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const BASE = "/organisations/o1/policies/p1";

const version = (overrides: Record<string, unknown>) => ({
  id: "v1",
  version: "1.0",
  effective_date: "2026-09-01",
  status: "PROCESSING",
  processing_stage: "EXTRACTING",
  original_filename: "repairs.pdf",
  file_size: 2048,
  uploaded_at: "2026-10-17T10:00:00Z",
  uploaded_by: "jane@example.org",
  ...overrides,
});

function policy(v: Record<string, unknown>) {
  return {
    id: "p1",
    name: "Repairs Policy",
    category: "Repairs",
    audience: "INTERNAL",
    source: null,
    created_at: "2026-10-17T10:00:00Z",
    updated_at: "2026-10-17T10:00:00Z",
    status: v.status,
    version_count: 1,
    owner: null,
    help_route: null,
    archived_at: null,
    archived_by: null,
    latest_version: v,
    current_version: v,
    active_version_id: null,
    versions: [v],
  };
}

describe("ProcessingSteps", () => {
  it("shows each step's state in symbols and in words", () => {
    render(<ProcessingSteps stage="INDEXING" />);
    const steps = within(screen.getByRole("list", { name: "Processing progress" })).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual([
      "Uploading✓ — complete",
      "Document processing✓ — complete",
      "Building knowledge● — in progress",
      "Making searchable○ — not started",
    ]);
  });

  it("marks the step that failed", () => {
    render(<ProcessingSteps stage="VALIDATING" failed />);
    expect(screen.getByText("Making searchable").closest("li")).toHaveTextContent("failed");
  });
});

describe("Live processing status", () => {
  it("updates the policy page by itself until processing finishes, then stops", async () => {
    let calls = 0;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => {
        calls += 1;
        const v =
          calls < 3
            ? version({ processing_stage: calls === 1 ? "EXTRACTING" : "INDEXING" })
            : version({ status: "DRAFT", processing_stage: "DONE", processed_at: "2026-10-17T10:01:00Z", chunk_count: 4 });
        return { status: 200, body: policy(v) };
      },
    });
    renderApp("/internal/policies/p1");
    expect(await screen.findByRole("list", { name: "Processing progress" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Mark ready for approval" })).toBeInTheDocument();
    expect(screen.getByText(/into 4 searchable passages/)).toBeInTheDocument();
    const settled = calls;
    await new Promise((r) => setTimeout(r, 100));
    expect(calls).toBe(settled); // no more polling once nothing is processing
  });

  it("offers administrators a retry for a failed version", async () => {
    let retried = false;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      [`GET ${BASE}`]: () => ({
        status: 200,
        body: policy(retried ? version({ processing_stage: "QUEUED" }) : version({ status: "FAILED", failure_reason: "Temporary problem", error_id: "abc123" })),
      }),
      [`POST ${BASE}/versions/v1/retry`]: () => {
        retried = true;
        return { status: 200, body: policy(version({ processing_stage: "QUEUED" })) };
      },
    });
    renderApp("/internal/policies/p1");
    expect(
      await screen.findByText("We couldn't process this policy. Your original document has not been deleted."),
    ).toBeInTheDocument();
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry processing" }));
    expect(await screen.findByText("Processing version 1.0 again.")).toBeInTheDocument();
    expect(retried).toBe(true);
  });

  it("refreshes the policy list while anything is processing", async () => {
    let calls = 0;
    const item = (status: string) => ({
      id: "p1",
      name: "Repairs Policy",
      category: "Repairs",
      audience: "INTERNAL",
      status,
      version: "1.0",
      effective_date: "2026-09-01",
      updated_at: "2026-10-17T10:00:00Z",
      owner: null,
    });
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies": () => {
        calls += 1;
        return { status: 200, body: { policies: [item(calls < 2 ? "PROCESSING" : "DRAFT")], categories: ["Repairs"] } };
      },
    });
    renderApp("/internal/policies");
    expect(await screen.findByText("Processing")).toBeInTheDocument();
    expect(await screen.findByText("Draft")).toBeInTheDocument();
  });
});

describe("Upload screen follows processing", () => {
  async function uploadOne() {
    await screen.findByRole("heading", { name: "Upload policy" });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["%PDF"], "repairs.pdf", { type: "application/pdf" }));
    await userEvent.type(screen.getByLabelText("Version"), "1.0");
    await userEvent.type(screen.getByLabelText("Effective date"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Category"), "Repairs");
    await userEvent.click(screen.getByRole("radio", { name: /Internal/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save & process" }));
  }

  it("shows progress, then that the policy is ready for review", async () => {
    let calls = 0;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies/categories": () => ({ status: 200, body: [] }),
      [`GET ${BASE}`]: () => {
        calls += 1;
        return { status: 200, body: policy(calls < 2 ? version({ processing_stage: "INDEXING" }) : version({ status: "DRAFT", processing_stage: "DONE" })) };
      },
    });
    vi.spyOn(apiModule, "uploadWithProgress").mockResolvedValue(policy(version({ processing_stage: "QUEUED" })) as never);
    renderApp("/internal/policies/new");
    await uploadOne();
    expect(await screen.findByText("Policy uploaded successfully.")).toBeInTheDocument();
    expect(screen.getByText("Processing policy")).toBeInTheDocument();
    expect(await screen.findByText("Processed and ready for review.")).toBeInTheDocument();
    expect(screen.getByText(/someone marks it ready for approval/)).toBeInTheDocument();
  });

  it("shows the failure screen with retry and back to policies", async () => {
    let retried = false;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1/policies/categories": () => ({ status: 200, body: [] }),
      [`GET ${BASE}`]: () => ({
        status: 200,
        body: policy(version({ status: "FAILED", processing_stage: "EXTRACTING", failure_reason: "We couldn't find enough text in this document." })),
      }),
      [`POST ${BASE}/versions/v1/retry`]: () => {
        retried = true;
        return { status: 200, body: policy(version({ processing_stage: "QUEUED" })) };
      },
    });
    vi.spyOn(apiModule, "uploadWithProgress").mockResolvedValue(policy(version({ processing_stage: "QUEUED" })) as never);
    renderApp("/internal/policies/new");
    await uploadOne();
    expect(await screen.findByRole("heading", { name: "We couldn't process this policy" })).toBeInTheDocument();
    expect(screen.getByText("Your original document has not been deleted.")).toBeInTheDocument();
    expect(screen.getByText("We couldn't find enough text in this document.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to policies" })).toBeInTheDocument();
    polling.intervalMs = 100000; // stop the screen flipping back to failed after the retry
    await userEvent.click(screen.getByRole("button", { name: "Retry processing" }));
    await waitFor(() => expect(retried).toBe(true));
    expect(await screen.findByText("Processing policy")).toBeInTheDocument();
  });
});
