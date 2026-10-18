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
      page: 4,
      excerpt: "Emergency repairs such as gas leaks are attended within 24 hours of a report.",
    },
  ],
  escalation: null,
  feedback: null,
  asked_at: new Date().toISOString(),
};

describe("Citations (US-018)", () => {
  it("open to show the exact passage used and a link to the policy", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions/q1": () => ({ status: 200, body: answered }),
    });
    renderApp("/internal/questions/q1");
    const toggle = await screen.findByRole("button", { name: /Repairs Policy.*View source/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveTextContent("Section: Emergency repairs · Page 4");
    expect(screen.queryByText(/gas leaks/)).not.toBeVisible();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/gas leaks are attended/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open the Repairs Policy" })).toHaveAttribute("href", "/internal/policies/p1");
  });
});

describe("Feedback (US-020)", () => {
  it("records Yes, then No with an optional reason", async () => {
    const sent: unknown[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions/q1": () => ({ status: 200, body: answered }),
      "PUT /organisations/o1/questions/q1/feedback": (body) => {
        sent.push(body);
        return { status: 200, body };
      },
    });
    renderApp("/internal/questions/q1");
    const group = await screen.findByRole("group", { name: "Was this answer helpful?" });
    await userEvent.click(within(group).getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("Thanks for your feedback.")).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Yes" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(within(group).getByRole("button", { name: "No" }));
    await userEvent.click(await screen.findByRole("radio", { name: "The answer was unclear" }));
    expect(sent).toEqual([
      { helpful: true, reason: null },
      { helpful: false, reason: null },
      { helpful: false, reason: "UNCLEAR" },
    ]);
    expect(screen.getByRole("radio", { name: "The answer was unclear" })).toBeChecked();
  });

  it("shows feedback already given and undoes a failed save", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions/q1": () => ({ status: 200, body: { ...answered, feedback: { helpful: true, reason: null } } }),
      "PUT /organisations/o1/questions/q1/feedback": () => ({ status: 500, body: { error: { code: "x", message: "x" } } }),
    });
    renderApp("/internal/questions/q1");
    const yes = await screen.findByRole("button", { name: "Yes" });
    expect(yes).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    expect(await screen.findByText("We couldn't save your feedback. Please try again.")).toBeInTheDocument();
    expect(yes).toHaveAttribute("aria-pressed", "true");
  });

  it("isn't offered when there was no answer", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions/q1": () => ({
        status: 200,
        body: { ...answered, status: "INSUFFICIENT_EVIDENCE", reason: "no_evidence", answer: null, citations: [] },
      }),
    });
    renderApp("/internal/questions/q1");
    expect(await screen.findByRole("heading", { name: "We couldn't find enough information to answer this." })).toBeInTheDocument();
    expect(screen.queryByText("Was this answer helpful?")).not.toBeInTheDocument();
  });
});

describe("My questions (US-019)", () => {
  const summary = (id: string, question: string, extra = {}) => ({
    id,
    question,
    status: "ANSWERED",
    reason: null,
    sources: ["Repairs Policy"],
    helpful: null,
    asked_at: new Date().toISOString(),
    ...extra,
  });

  it("lists my questions with status, date and sources, and loads older ones", async () => {
    const urls: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions": (_body, url) => {
        urls.push(url.search);
        return url.search.includes("before=q2")
          ? { status: 200, body: { questions: [summary("q3", "Older question")], next_before: null } }
          : {
              status: 200,
              body: {
                questions: [
                  summary("q1", "How quickly are emergency repairs attended?", { helpful: true }),
                  summary("q2", "Can tenants keep pets?", { status: "INSUFFICIENT_EVIDENCE", sources: [] }),
                ],
                next_before: "q2",
              },
            };
      },
    });
    renderApp("/internal/questions");
    const link = await screen.findByRole("link", { name: "How quickly are emergency repairs attended?" });
    expect(link).toHaveAttribute("href", "/internal/questions/q1");
    const first = link.closest("li")!;
    expect(first).toHaveTextContent("Answered");
    expect(first).toHaveTextContent("today");
    expect(first).toHaveTextContent("Sources: Repairs Policy");
    expect(first).toHaveTextContent("You found this helpful");
    expect(screen.getByRole("link", { name: "Can tenants keep pets?" }).closest("li")).toHaveTextContent("Not enough information");
    expect(screen.getByRole("link", { name: "Questions" })).toHaveAttribute("aria-current", "page");

    await userEvent.click(screen.getByRole("button", { name: "Show older questions" }));
    expect(await screen.findByRole("link", { name: "Older question" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show older questions" })).not.toBeInTheDocument();
  });

  it("filters by status and search", async () => {
    const urls: string[] = [];
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions": (_body, url) => {
        urls.push(url.search);
        return { status: 200, body: { questions: [], next_before: null } };
      },
    });
    renderApp("/internal/questions");
    expect(await screen.findByText("You haven't asked any questions yet")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "INSUFFICIENT_EVIDENCE");
    await userEvent.type(screen.getByLabelText("Search questions"), "pets");
    expect(await screen.findByText("No questions match these filters")).toBeInTheDocument();
    await vi.waitFor(() => expect(urls[urls.length - 1]).toMatch(/status=INSUFFICIENT_EVIDENCE.*q=pets|q=pets.*status=INSUFFICIENT_EVIDENCE/));
  });

  it("says when a question is no longer available", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1/questions/q9": () => ({ status: 404, body: { error: { code: "not_found", message: "x" } } }),
    });
    renderApp("/internal/questions/q9");
    expect(await screen.findByText("This question is no longer available.")).toBeInTheDocument();
  });
});
