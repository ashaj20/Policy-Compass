import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { slugify, validateSlug } from "../../lib/slug";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());
beforeAll(() => {
  // jsdom has no object URLs; the logo preview uses them.
  URL.createObjectURL = () => "blob:preview";
  URL.revokeObjectURL = () => {};
});

const newUser = { id: "u1", email: "jane@example.org", memberships: [] };
const membership = {
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
  organisation_slug: "riverside-housing",
  role: "ADMIN",
};
const admin = { ...newUser, memberships: [membership] };
const createdOrg = { id: "o1", name: "Riverside Housing", slug: "riverside-housing", website: null, logo_url: null, role: "ADMIN" };

describe("slug helpers", () => {
  it("suggests a URL-safe slug from the name", () => {
    expect(slugify("Riverside Housing")).toBe("riverside-housing");
    expect(slugify("  Café & Care Ltd.  ")).toBe("cafe-and-care-ltd");
    expect(slugify("---")).toBe("");
  });

  it("validates slugs like the API", () => {
    expect(validateSlug("riverside-housing")).toBeUndefined();
    expect(validateSlug("Riverside")).toBe("Use lowercase letters only");
    expect(validateSlug("ab")).toBe("Use at least 3 characters");
    expect(validateSlug("river--side")).toMatch(/single hyphens/);
  });
});

describe("Create organisation", () => {
  it("is where signed-in people without an organisation land", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: newUser }) });
    renderApp("/internal");
    expect(await screen.findByRole("heading", { name: "Create your organisation" })).toBeInTheDocument();
    expect(screen.getByText("Organisation").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("fills the public URL from the name and shows whether it is available", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: newUser }),
      "GET /organisations/slug-available": (_, url) =>
        url.searchParams.get("slug") === "riverside-housing"
          ? { status: 200, body: { available: false, message: "This URL is already taken. Please choose another" } }
          : { status: 200, body: { available: true, message: null } },
    });
    renderApp("/internal/setup/organisation");
    await userEvent.type(await screen.findByLabelText("Organisation name"), "Riverside Housing");
    expect(screen.getByLabelText("Public URL")).toHaveValue("riverside-housing");
    expect(await screen.findByText(/This URL is already taken/)).toBeInTheDocument();

    const slugField = screen.getByLabelText("Public URL");
    await userEvent.clear(slugField);
    await userEvent.type(slugField, "riverside-homes");
    expect(await screen.findByText("✓ Available")).toBeInTheDocument();
    // Editing the slug by hand stops it following the name.
    await userEvent.type(screen.getByLabelText("Organisation name"), " Group");
    expect(slugField).toHaveValue("riverside-homes");
  });

  it("validates required fields before calling the API", async () => {
    const spy = mockApi({ "GET /auth/me": () => ({ status: 200, body: newUser }) });
    renderApp("/internal/setup/organisation");
    await userEvent.type(await screen.findByLabelText("Website (optional)"), "not a website");
    await userEvent.click(screen.getByRole("button", { name: "Create organisation" }));
    expect(screen.getByText(/Enter your organisation's name/)).toBeInTheDocument();
    expect(screen.getByText(/Enter a public URL/)).toBeInTheDocument();
    expect(screen.getByText(/Enter a valid website address/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("rejects logos of the wrong type or size before uploading", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: newUser }) });
    renderApp("/internal/setup/organisation");
    const input = (await screen.findByText("Upload logo")).querySelector("input")!;
    await userEvent.upload(input, new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }), { applyAccept: false });
    expect(screen.getByRole("alert")).toHaveTextContent("PNG, JPEG or WebP");

    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
    await userEvent.upload(input, big);
    expect(screen.getByRole("alert")).toHaveTextContent("2 MB or smaller");
  });

  it("creates the organisation, uploads the logo and opens the workspace", async () => {
    let created: unknown;
    let logoUploaded = false;
    let me = newUser as typeof newUser | typeof admin;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: me }),
      "GET /organisations/slug-available": () => ({ status: 200, body: { available: true, message: null } }),
      "POST /organisations": (body) => {
        created = body;
        me = admin;
        return { status: 201, body: createdOrg };
      },
      "PUT /organisations/o1/logo": (body) => {
        logoUploaded = body instanceof FormData && body.get("file") instanceof File;
        return { status: 200, body: createdOrg };
      },
    });
    renderApp("/internal/setup/organisation");
    await userEvent.type(await screen.findByLabelText("Organisation name"), "Riverside Housing");
    await userEvent.type(screen.getByLabelText("Website (optional)"), "www.riversidehousing.example");
    const input = screen.getByText("Upload logo").querySelector("input")!;
    await userEvent.upload(input, new File(["png"], "logo.png", { type: "image/png" }));
    expect(screen.getByText("logo.png")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create organisation" }));

    expect(await screen.findByText("Your organisation has been created.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Riverside Housing" })).toBeInTheDocument();
    expect(screen.getByText(/· Administrator/)).toBeInTheDocument();
    expect(created).toEqual({ name: "Riverside Housing", slug: "riverside-housing", website: "www.riversidehousing.example" });
    expect(logoUploaded).toBe(true);
  });

  it("shows the server's message when the URL was taken in the meantime", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: newUser }),
      "GET /organisations/slug-available": () => ({ status: 200, body: { available: true, message: null } }),
      "POST /organisations": () => ({
        status: 409,
        body: {
          error: {
            code: "slug_taken",
            message: "This URL is already taken. Please choose another",
            fields: { slug: "This URL is already taken. Please choose another" },
          },
        },
      }),
    });
    renderApp("/internal/setup/organisation");
    await userEvent.type(await screen.findByLabelText("Organisation name"), "Riverside Housing");
    await userEvent.click(screen.getByRole("button", { name: "Create organisation" }));
    await waitFor(() => expect(screen.getByLabelText("Public URL")).toHaveAttribute("aria-invalid", "true"));
  });

  it("sends people who already have an organisation to their workspace", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: admin }) });
    renderApp("/internal/setup/organisation");
    expect(await screen.findByRole("heading", { name: "Riverside Housing" })).toBeInTheDocument();
  });
});

describe("Public page", () => {
  it("shows the organisation for its public URL without signing in", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 401, body: { error: { code: "not_authenticated", message: "x" } } }),
      "GET /public/organisations/riverside-housing": () => ({
        status: 200,
        body: { name: "Riverside Housing", slug: "riverside-housing", website: null, logo_url: null, primary_colour: "#0b6e4f", brand_text_colour: "#ffffff" },
      }),
    });
    renderApp("/p/riverside-housing");
    expect(await screen.findByText("Riverside Housing")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How can we help?" })).toBeInTheDocument();
  });

  it("explains when no organisation has that URL", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 401, body: { error: { code: "not_authenticated", message: "x" } } }),
      "GET /public/organisations/nobody": () => ({
        status: 404,
        body: { error: { code: "not_found", message: "We couldn't find this organisation's Policy Compass page." } },
      }),
    });
    renderApp("/p/nobody");
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't find this organisation");
  });
});
