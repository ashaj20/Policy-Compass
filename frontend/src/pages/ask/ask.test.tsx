import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const staff = {
  id: "u2",
  email: "john@example.org",
  memberships: [
    { organisation_id: "o1", organisation_name: "Riverside Housing", organisation_slug: "riverside-housing", role: "STAFF" },
  ],
};

const answered = {
  id: "q1",
  question: "How quickly are emergency repairs attended?",
  status: "ANSWERED",
  reason: null,
  answer: "Emergency repairs are attended within 24 hours of a report.",
  citations: [
    {
      policy_id: "p1",
      policy_name: "Repairs Policy",
      version_id: "v1",
      version_label: "3.2",
      effective_date: "2026-09-01",
      section: "Emergency repairs",
      page: null,
      excerpt: "Emergency repairs such as gas leaks are attended within 24 hours of a report.",
    },
  ],
  asked_at: "2026-10-18T10:00:00Z",
};

describe("Ask a question", () => {
  it("asks a question and shows the answer separately from its sources", async () => {
    const asked: unknown[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "POST /organisations/o1/questions": (body) => {
        asked.push(body);
        return { status: 201, body: answered };
      },
    });
    renderApp("/internal/ask");
    const box = await screen.findByLabelText("What would you like to know?");
    await userEvent.type(box, "How quickly are emergency repairs attended?{Enter}");

    const answer = await screen.findByRole("region", { name: "Answer" });
    expect(answer).toHaveTextContent("within 24 hours");
    const sources = screen.getByRole("region", { name: "Sources" });
    expect(within(sources).getByText("Repairs Policy")).toBeInTheDocument();
    expect(sources).toHaveTextContent("Version 3.2 · Effective 01 September 2026");
    expect(sources).toHaveTextContent("Section: Emergency repairs");
    expect(answer).not.toHaveTextContent("Repairs Policy");
    expect(asked).toEqual([{ question: "How quickly are emergency repairs attended?" }]);
    expect(screen.getByRole("link", { name: "Ask Question" })).toHaveAttribute("aria-current", "page");
  });

  it("checks the question before sending it", async () => {
    const post = vi.fn(() => ({ status: 201, body: answered }));
    mockApi({ "GET /auth/me": () => ({ status: 200, body: staff }), "POST /organisations/o1/questions": post });
    renderApp("/internal/ask");
    await userEvent.click(await screen.findByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a question to get started");
    await userEvent.type(screen.getByLabelText("What would you like to know?"), "hi{Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("Please ask a fuller question");
    expect(post).not.toHaveBeenCalled();
  });

  it("asks an example question when it is chosen", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "POST /organisations/o1/questions": () => ({ status: 201, body: answered }),
    });
    renderApp("/internal/ask");
    await userEvent.click(await screen.findByRole("button", { name: "How do I report a repair?" }));
    expect(await screen.findByRole("region", { name: "Answer" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ask another question" }));
    expect(screen.queryByRole("region", { name: "Answer" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("What would you like to know?")).toHaveValue("");
  });

  it("says plainly when there isn't enough information", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "POST /organisations/o1/questions": () => ({
        status: 201,
        body: { ...answered, status: "INSUFFICIENT_EVIDENCE", reason: "no_evidence", answer: null, citations: [] },
      }),
    });
    renderApp("/internal/ask");
    await userEvent.type(await screen.findByLabelText("What would you like to know?"), "Can tenants keep pets?{Enter}");
    expect(await screen.findByText("We couldn't find enough information to answer this.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("asks a question typed on the dashboard", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/dashboard": () => ({
        status: 200,
        body: {
          counts: { total: 1, active: 1, awaiting_approval: 0, drafts_to_review: 0, processing: 0, failed: 0, archived: 0 },
          attention: [],
          setup: [],
        },
      }),
      "POST /organisations/o1/questions": () => ({ status: 201, body: answered }),
    });
    renderApp("/internal");
    await userEvent.type(await screen.findByLabelText("Ask a policy question"), "How quickly are emergency repairs attended?{Enter}");
    expect(await screen.findByRole("region", { name: "Answer" })).toHaveTextContent("within 24 hours");
    expect(screen.getByRole("heading", { name: "Ask a policy question", level: 1 })).toBeInTheDocument();
  });
});
