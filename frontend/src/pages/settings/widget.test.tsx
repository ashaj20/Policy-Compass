import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp, unauthenticated } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role,
});
const publicInfo = (accepting: boolean) => ({
  name: "Riverside Housing",
  slug: "riverside-housing",
  website: "https://riverside.example",
  logo_url: null,
  primary_colour: "#0b6e4f",
  brand_text_colour: "#ffffff",
  accepting_questions: accepting,
  topics: [],
  help_route: null,
});

describe("Website widget settings (US-030)", () => {
  it("gives administrators the widget and embed code with previews", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] } }),
      "GET /public/organisations/riverside-housing": () => ({ status: 200, body: publicInfo(true) }),
    });
    renderApp("/internal/settings/widget");
    const code = await screen.findByLabelText("Widget code");
    expect(code).toHaveValue(
      `<script src="${window.location.origin}/widget.js" data-organisation="riverside-housing" data-colour="#0b6e4f" async></script>`,
    );
    expect(screen.getByLabelText("Embed code")).toHaveValue(
      `<iframe src="${window.location.origin}/p/riverside-housing/widget" title="Ask a question" width="100%" height="640" style="border:0"></iframe>`,
    );
    expect(screen.getByRole("link", { name: "Preview the button on a sample web page" })).toHaveAttribute(
      "href",
      "/widget-demo.html?org=riverside-housing&colour=%230b6e4f",
    );
    expect(screen.queryByText("Your public page isn't answering questions yet.")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Website widget" })).toHaveAttribute("aria-current", "page");
  });

  it("warns when the public page can't answer yet", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] } }),
      "GET /public/organisations/riverside-housing": () => ({ status: 200, body: publicInfo(false) }),
    });
    renderApp("/internal/settings/widget");
    expect(await screen.findByText("Your public page isn't answering questions yet.")).toBeInTheDocument();
  });

  it("is for administrators only", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] } }) });
    renderApp("/internal/settings/widget");
    expect(await screen.findByText("You don't have permission to manage the website widget.")).toBeInTheDocument();
  });
});

describe("Embedded public page (US-030)", () => {
  it("is compact, opens outside links in a new tab, and still never shows internal navigation", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "GET /public/organisations/riverside-housing": () => ({
        status: 200,
        body: { ...publicInfo(true), help_route: { label: "Customer Services", route_type: "WEBSITE", destination: "https://help.example", description: null } },
      }),
    });
    const { container } = renderApp("/p/riverside-housing/widget");
    expect(await screen.findByRole("heading", { name: "How can we help?" })).toBeInTheDocument();
    expect(container.querySelector(".pc-public--embedded")).not.toBeNull();
    expect(screen.queryByRole("link", { name: /Visit Riverside Housing's website/ })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Need more help?" })).getByRole("link", { name: "Customer Services" })).toBeInTheDocument();
    expect(document.head.querySelector("base")?.getAttribute("target")).toBe("_blank");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
