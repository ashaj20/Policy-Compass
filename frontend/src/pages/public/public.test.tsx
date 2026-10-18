import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp, unauthenticated } from "../../test/utils";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());

const org = {
  name: "Riverside Housing",
  slug: "riverside-housing",
  website: "https://riverside.example",
  logo_url: null,
  primary_colour: "#0b6e4f",
  brand_text_colour: "#ffffff",
  accepting_questions: true,
  topics: ["Complaints", "Repairs"],
  help_route: { label: "Customer Services", route_type: "PHONE", destination: "0161 555 0000", description: "Mon–Fri 9am–5pm" },
};

const answered = {
  id: "q1",
  question: "How do I report a repair?",
  status: "ANSWERED",
  reason: null,
  answer: "You can report a repair online at any time of day.",
  citations: [
    {
      policy_name: "Repairs Policy",
      version_label: "2.1",
      effective_date: "2026-09-01",
      section: "Reporting a repair",
      page: null,
      excerpt: "Repairs can be reported online at any time of day.",
    },
  ],
  escalation: null,
  feedback: null,
};

const insufficient = {
  ...answered,
  id: "q2",
  question: "Can I keep a pet?",
  status: "INSUFFICIENT_EVIDENCE",
  reason: "no_evidence",
  answer: null,
  citations: [],
};

function setup(post: (body: unknown) => { status: number; body?: unknown }, extra = {}) {
  return mockApi({
    "GET /auth/me": () => unauthenticated,
    "GET /public/organisations/riverside-housing": () => ({ status: 200, body: { ...org, ...extra } }),
    "POST /public/organisations/riverside-housing/questions": post,
    "PUT /public/organisations/riverside-housing/questions/q1/feedback": (body) => ({ status: 200, body }),
  });
}

async function askQuestion(text: string) {
  await userEvent.type(await screen.findByLabelText("What would you like to know?"), `${text}{Enter}`);
}

describe("Public page (US-026)", () => {
  it("invites questions with topics and a help route, without signing in or internal navigation", async () => {
    setup(() => ({ status: 201, body: answered }));
    renderApp("/p/riverside-housing");
    expect(await screen.findByRole("heading", { name: "How can we help?" })).toBeInTheDocument();
    expect(screen.getByText("You can ask about: Complaints, Repairs.")).toBeInTheDocument();
    const help = screen.getByRole("region", { name: "Need more help?" });
    expect(within(help).getByRole("link", { name: "Customer Services" })).toHaveAttribute("href", "tel:01615550000");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByText("Policies")).not.toBeInTheDocument();
  });

  it("says when the page is still being set up", async () => {
    setup(() => ({ status: 201, body: answered }), { accepting_questions: false, topics: [] });
    renderApp("/p/riverside-housing");
    expect(await screen.findByText(/policy questions page is being set up/)).toBeInTheDocument();
    expect(screen.queryByLabelText("What would you like to know?")).not.toBeInTheDocument();
  });
});

describe("Public questions (US-027)", () => {
  it("answers with public sources and takes feedback", async () => {
    const sent: unknown[] = [];
    setup((body) => {
      sent.push(body);
      return { status: 201, body: answered };
    });
    renderApp("/p/riverside-housing");
    await askQuestion("How do I report a repair?");
    const answer = await screen.findByRole("region", { name: "Answer" });
    expect(answer).toHaveTextContent("report a repair online");
    expect(answer).toHaveTextContent("Based only on Riverside Housing's approved public policies.");
    const sources = screen.getByRole("region", { name: "Sources" });
    await userEvent.click(within(sources).getByRole("button", { name: /Repairs Policy/ }));
    expect(within(sources).getByText(/can be reported online/)).toBeVisible();
    expect(within(sources).queryByRole("link")).not.toBeInTheDocument();
    expect(sent).toEqual([{ question: "How do I report a repair?" }]);

    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("Thanks for your feedback.")).toBeInTheDocument();
  });

  it("shows the public help route when it can't answer", async () => {
    setup(() => ({
      status: 201,
      body: {
        ...insufficient,
        escalation: { kind: "help_route", label: "Repairs Helpdesk", route_type: "EMAIL", destination: "repairs@example.org", description: null },
      },
    }));
    renderApp("/p/riverside-housing");
    await askQuestion("Can I keep a pet?");
    expect(
      await screen.findByRole("heading", { name: "We couldn't find enough information in our approved policies to answer this." }),
    ).toBeInTheDocument();
    const help = screen.getByRole("region", { name: "Need help?" });
    expect(within(help).getByRole("link", { name: "Send an email" })).toHaveAttribute("href", "mailto:repairs@example.org");
    expect(screen.queryByText("Was this answer helpful?")).not.toBeInTheDocument();
  });

  it("explains the generic route when no help route exists", async () => {
    setup(() => ({ status: 201, body: insufficient }), { help_route: null });
    renderApp("/p/riverside-housing");
    await askQuestion("Can I keep a pet?");
    expect(await screen.findByText("Please contact the organisation through its main customer support channel.")).toBeInTheDocument();
  });

  it("explains rate limits plainly", async () => {
    setup(() => ({
      status: 429,
      body: { error: { code: "too_many_questions", message: "You've asked a lot of questions in a short time. Please wait a minute and try again." } },
    }));
    renderApp("/p/riverside-housing");
    await askQuestion("How do I report a repair?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Please wait a minute and try again.");
  });

  it("keeps this tab's questions so they can be reopened", async () => {
    let n = 0;
    setup(() => ({ status: 201, body: n++ === 0 ? answered : insufficient }));
    renderApp("/p/riverside-housing");
    await askQuestion("How do I report a repair?");
    await screen.findByRole("region", { name: "Answer" });
    await userEvent.click(screen.getByRole("button", { name: "Ask another question" }));
    await askQuestion("Can I keep a pet?");
    await screen.findByRole("heading", { name: "We couldn't find enough information to answer this." });

    const history = screen.getByRole("region", { name: "Your questions" });
    const items = within(history).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "Can I keep a pet?We couldn't find enough information",
      "How do I report a repair?Answered",
    ]);
    await userEvent.click(within(history).getByRole("button", { name: "How do I report a repair?" }));
    expect(await screen.findByRole("region", { name: "Answer" })).toHaveTextContent("report a repair online");
    expect(JSON.parse(sessionStorage.getItem("pc-public-history:riverside-housing")!)).toHaveLength(2);
  });
});
