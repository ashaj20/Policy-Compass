import { screen, within } from "@testing-library/react";
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

describe("Data and retention", () => {
  it("lists what is kept and for how long, for every member", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /retention": () => ({
        status: 200,
        body: [
          { data: "Questions and answers", period: "12 months", detail: "Deleted automatically after 12 months." },
          { data: "Audit trail", period: "6 years", detail: "A permanent record of administrative changes." },
        ],
      }),
    });
    renderApp("/internal/settings/data");
    const row = (await screen.findByText("Audit trail")).closest("tr")!;
    expect(within(row).getByText("6 years")).toBeInTheDocument();
    expect(screen.getByText("Please don't include personal information in questions.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data & retention" })).toHaveAttribute("aria-current", "page");
  });
});