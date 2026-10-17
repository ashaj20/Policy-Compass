import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import * as apiModule from "../../lib/api";
import { nameFromFilename, validatePolicyFile } from "../../lib/policy";
import { mockApi, renderApp } from "../../test/utils";

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const staff = { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] };

const uploadedPolicy = {
  id: "p1",
  name: "Emergency Repairs Policy",
  category: "Repairs",
  audience: "INTERNAL",
  source: null,
  created_at: "2026-10-17T10:00:00Z",
  latest_version: {
    id: "v1",
    version: "3.2",
    effective_date: "2026-09-01",
    status: "PROCESSING",
    original_filename: "emergency-repairs-policy.pdf",
    file_size: 2048,
    uploaded_at: "2026-10-17T10:00:00Z",
    uploaded_by: "jane@example.org",
  },
};

const pdf = () => new File(["%PDF-1.4 test"], "emergency-repairs-policy.pdf", { type: "application/pdf" });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let uploadSpy: MockInstance<(...args: any[]) => Promise<unknown>>;
beforeEach(() => {
  uploadSpy = vi.spyOn(apiModule, "uploadWithProgress");
});
afterEach(() => vi.restoreAllMocks());

function mockAdmin() {
  return mockApi({
    "GET /auth/me": () => ({ status: 200, body: admin }),
    "GET /organisations/o1/policies/categories": () => ({ status: 200, body: ["Repairs", "Rent"] }),
  });
}

async function chooseFile(file: File) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  await userEvent.upload(input, file, { applyAccept: false });
}

describe("helpers", () => {
  it("suggests a name from the file name and checks file types", () => {
    expect(nameFromFilename("emergency_repairs-policy v3.pdf")).toBe("Emergency repairs policy v3");
    expect(validatePolicyFile(new File(["x"], "a.txt"))).toMatch(/isn't supported/);
    expect(validatePolicyFile(new File([""], "a.pdf"))).toMatch(/empty/);
    expect(validatePolicyFile(new File(["x"], "a.DOCX"))).toBeUndefined();
  });
});

describe("Upload policy", () => {
  it("uploads a document with its details and shows it is processing", async () => {
    mockAdmin();
    uploadSpy.mockImplementation(async (_path: string, _body: FormData, onProgress: (p: number) => void) => {
      onProgress(63);
      return uploadedPolicy as never;
    });
    renderApp("/internal/policies/new");

    await screen.findByRole("heading", { name: "Upload policy" });
    await chooseFile(pdf());
    expect(screen.getByText("emergency-repairs-policy.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Policy name")).toHaveValue("Emergency repairs policy");

    await userEvent.clear(screen.getByLabelText("Policy name"));
    await userEvent.type(screen.getByLabelText("Policy name"), "Emergency Repairs Policy");
    await userEvent.type(screen.getByLabelText("Version"), "3.2");
    await userEvent.type(screen.getByLabelText("Effective date"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Category"), "Repairs");
    await userEvent.click(screen.getByRole("radio", { name: /Internal/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save & process" }));

    expect(await screen.findByText("Policy uploaded successfully.")).toBeInTheDocument();
    expect(screen.getByText(/Processing policy/)).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Internal", { selector: ".pc-badge" })).toBeInTheDocument();

    const [path, body] = uploadSpy.mock.calls[0] as unknown as [string, FormData];
    expect(path).toBe("/organisations/o1/policies");
    expect(body.get("name")).toBe("Emergency Repairs Policy");
    expect(body.get("version")).toBe("3.2");
    expect(body.get("effective_date")).toBe("2026-09-01");
    expect(body.get("audience")).toBe("INTERNAL");
    expect(body.get("category")).toBe("Repairs");
    expect(body.get("file")).toBeInstanceOf(File);
  });

  it("validates required details before uploading", async () => {
    mockAdmin();
    renderApp("/internal/policies/new");
    await userEvent.click(await screen.findByRole("button", { name: "Save & process" }));
    expect(screen.getByText(/Choose a PDF or Word document to upload/)).toBeInTheDocument();
    expect(screen.getByText(/Enter the policy name/)).toBeInTheDocument();
    expect(screen.getByText(/Enter the version/)).toBeInTheDocument();
    expect(screen.getByText(/Enter the date this version takes effect/)).toBeInTheDocument();
    expect(screen.getByText(/Choose who this policy is for/)).toBeInTheDocument();
    expect(screen.getByText(/Enter a category/)).toBeInTheDocument();
    expect(uploadSpy).not.toHaveBeenCalled();
  });

  it("rejects unsupported file types straight away", async () => {
    mockAdmin();
    renderApp("/internal/policies/new");
    await screen.findByRole("heading", { name: "Upload policy" });
    await chooseFile(new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(screen.getByRole("alert")).toHaveTextContent("This file type isn't supported");
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
  });

  it("shows owner and help-route guidance depending on the audience", async () => {
    mockAdmin();
    renderApp("/internal/policies/new");
    await screen.findByRole("heading", { name: "Upload policy" });
    expect(screen.queryByText("Internal policy owner")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Internal/ }));
    expect(screen.getByText("Internal policy owner")).toBeInTheDocument();
    expect(screen.queryByText("Public help route")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Public/ }));
    expect(screen.queryByText("Internal policy owner")).not.toBeInTheDocument();
    expect(screen.getByText("Public help route")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Both/ }));
    expect(screen.getByText("Internal policy owner")).toBeInTheDocument();
    expect(screen.getByText("Public help route")).toBeInTheDocument();
  });

  it("shows the server's error for a duplicate policy name", async () => {
    mockAdmin();
    const msg = "A policy with this name already exists. To update it, upload a new version from the policy's page.";
    uploadSpy.mockRejectedValue(new apiModule.ApiError(409, "policy_exists", msg, { name: msg }));
    renderApp("/internal/policies/new");
    await screen.findByRole("heading", { name: "Upload policy" });
    await chooseFile(pdf());
    await userEvent.type(screen.getByLabelText("Version"), "3.2");
    await userEvent.type(screen.getByLabelText("Effective date"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Category"), "Repairs");
    await userEvent.click(screen.getByRole("radio", { name: /Both/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save & process" }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("already exists"))).toBe(true);
    expect(screen.getByLabelText("Policy name")).toHaveAttribute("aria-invalid", "true");
  });

  it("is not available to staff", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: staff }) });
    renderApp("/internal/policies/new");
    expect(await screen.findByText("You don't have permission to upload policies.")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: "Upload policy" })).not.toBeInTheDocument();
  });
});
