import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF", name = "Riverside Housing") => ({
  organisation_id: "o1",
  organisation_name: name,
  organisation_slug: "riverside-housing",
  role,
});
const admin = { id: "u1", email: "jane@example.org", memberships: [membership("ADMIN")] };
const staff = { id: "u2", email: "john@example.org", memberships: [membership("STAFF")] };
const org = {
  id: "o1",
  name: "Riverside Housing",
  slug: "riverside-housing",
  website: "https://www.riversidehousing.example",
  logo_url: null as string | null,
  role: "ADMIN",
};

describe("Organisation settings", () => {
  it("lets an administrator edit and save details", async () => {
    let sent: unknown;
    let me = admin;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: me }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
      "PATCH /organisations/o1": (body) => {
        sent = body;
        me = { ...admin, memberships: [membership("ADMIN", "Riverside Homes")] };
        return { status: 200, body: { ...org, name: "Riverside Homes", website: null } };
      },
    });
    renderApp("/internal/settings");
    const name = await screen.findByLabelText("Organisation name");
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled(); // nothing changed yet

    await userEvent.clear(name);
    await userEvent.type(name, "Riverside Homes");
    await userEvent.clear(screen.getByLabelText("Website (optional)"));
    await userEvent.click(save);

    expect(await screen.findByText("Your changes have been saved.")).toBeInTheDocument();
    expect(sent).toEqual({ name: "Riverside Homes", website: "" });
    // The top bar picks up the new name.
    expect(await screen.findByText("Riverside Homes", { selector: ".pc-topbar__org" })).toBeInTheDocument();
  });

  it("validates before saving", async () => {
    const spy = mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
    });
    renderApp("/internal/settings");
    await userEvent.clear(await screen.findByLabelText("Organisation name"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText(/Enter your organisation's name/)).toBeInTheDocument();
    expect(spy.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("uploads and removes the logo", async () => {
    let current = org;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: current }),
      "PUT /organisations/o1/logo": () => {
        current = { ...org, logo_url: "/api/public/organisations/riverside-housing/logo?v=1" };
        return { status: 200, body: current };
      },
      "DELETE /organisations/o1/logo": () => ({ status: 200, body: { ...org, logo_url: null } }),
    });
    renderApp("/internal/settings");
    const logo = await screen.findByRole("region", { name: "Logo" });
    expect(within(logo).getByText("No logo")).toBeInTheDocument();
    const input = within(logo).getByText("Upload logo").querySelector("input")!;
    await userEvent.upload(input, new File(["png"], "logo.png", { type: "image/png" }));
    expect(await within(logo).findByText("Your logo has been updated.")).toBeInTheDocument();
    expect(within(logo).getByRole("img", { name: "Riverside Housing logo" })).toBeInTheDocument();

    await userEvent.click(within(logo).getByRole("button", { name: "Remove logo" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove logo" }));
    expect(await within(logo).findByText("Your logo has been removed.")).toBeInTheDocument();
  });

  it("rejects an unsuitable logo before uploading", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
    });
    renderApp("/internal/settings");
    const logo = await screen.findByRole("region", { name: "Logo" });
    const input = within(logo).getByText("Upload logo").querySelector("input")!;
    await userEvent.upload(input, new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }), { applyAccept: false });
    expect(within(logo).getByRole("alert")).toHaveTextContent("PNG, JPEG or WebP");
  });

  it("shows the public URL", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
    });
    renderApp("/internal/settings");
    const section = await screen.findByRole("region", { name: "Public URL" });
    expect(within(section).getByRole("link")).toHaveAttribute("href", "/p/riverside-housing");
    expect(within(section).getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("is read-only for staff members", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1": () => ({ status: 200, body: { ...org, role: "STAFF" } }),
    });
    renderApp("/internal/settings");
    expect(await screen.findByText("https://www.riversidehousing.example")).toBeInTheDocument();
    expect(screen.getByText(/Only administrators can change them/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Organisation name")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.queryByText("Upload logo")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage members" })).not.toBeInTheDocument();
  });

  it("offers a retry if settings fail to load", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 500, body: { error: { code: "internal_error", message: "x", error_id: "abc123" } } }),
    });
    renderApp("/internal/settings");
    expect(await screen.findByText("We couldn't load your settings. Please try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
  });
});

describe("Changing the public URL", () => {
  it("warns that links may break, then changes the URL", async () => {
    let sent: unknown;
    let me = admin;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: me }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
      "GET /organisations/slug-available": () => ({ status: 200, body: { available: true, message: null } }),
      "PUT /organisations/o1/slug": (body) => {
        sent = body;
        me = { ...admin, memberships: [{ ...membership("ADMIN"), organisation_slug: "riverside-homes" }] };
        return { status: 200, body: { ...org, slug: "riverside-homes" } };
      },
    });
    renderApp("/internal/settings");
    const section = await screen.findByRole("region", { name: "Public URL" });
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    const field = within(section).getByLabelText("New public URL");
    expect(field).toHaveFocus();
    await userEvent.clear(field);
    await userEvent.type(field, "riverside-homes");
    expect(await within(section).findByText("✓ Available")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));

    const dialog = screen.getByRole("dialog", { name: "Change your public URL?" });
    expect(dialog).toHaveTextContent("Changing your public URL may break existing links.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(sent).toBeUndefined(); // nothing changes until confirmed
    await userEvent.click(within(dialog).getByRole("button", { name: "Change URL" }));

    expect(await within(section).findByText("Your public URL has been changed.")).toBeInTheDocument();
    expect(sent).toEqual({ slug: "riverside-homes" });
    expect(within(section).getByRole("link")).toHaveAttribute("href", "/p/riverside-homes");
  });

  it("cancelling the warning leaves the URL unchanged", async () => {
    const spy = mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
      "GET /organisations/slug-available": () => ({ status: 200, body: { available: true, message: null } }),
    });
    renderApp("/internal/settings");
    const section = await screen.findByRole("region", { name: "Public URL" });
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    const field = within(section).getByLabelText("New public URL");
    await userEvent.clear(field);
    await userEvent.type(field, "riverside-homes");
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(spy.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("rejects an invalid or taken URL before asking to confirm", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
      "GET /organisations/slug-available": () => ({
        status: 200,
        body: { available: false, message: "This URL is already taken. Please choose another" },
      }),
    });
    renderApp("/internal/settings");
    const section = await screen.findByRole("region", { name: "Public URL" });
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    const field = within(section).getByLabelText("New public URL");
    await userEvent.clear(field);
    await userEvent.type(field, "river_side");
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    expect(within(section).getByText(/Use only lowercase letters/)).toBeInTheDocument();

    await userEvent.clear(field);
    await userEvent.type(field, "other-org");
    expect(await within(section).findByText(/✕ This URL is already taken/)).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Change URL" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is not offered to staff members", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1": () => ({ status: 200, body: { ...org, role: "STAFF" } }),
    });
    renderApp("/internal/settings");
    const section = await screen.findByRole("region", { name: "Public URL" });
    expect(within(section).queryByRole("button", { name: "Change URL" })).not.toBeInTheDocument();
  });
});