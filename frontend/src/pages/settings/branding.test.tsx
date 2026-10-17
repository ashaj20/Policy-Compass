import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { contrastRatio, meetsContrast, normaliseHex, textColourFor } from "../../lib/colour";
import { mockApi, renderApp } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const membership = (role: "ADMIN" | "STAFF") => ({
  organisation_id: "o1",
  organisation_name: "Riverside Housing",
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
  primary_colour: "#1f5aa6",
  brand_text_colour: "#ffffff",
  colour_meets_contrast: true,
  role: "ADMIN",
};

describe("colour helpers", () => {
  it("normalises hex codes and picks readable text", () => {
    expect(normaliseHex("#1F5AA6")).toBe("#1f5aa6");
    expect(normaliseHex("f60")).toBe("#ff6600");
    expect(normaliseHex("blue")).toBeUndefined();
    expect(textColourFor("#1f5aa6")).toBe("#ffffff");
    expect(textColourFor("#ffd166")).toBe("#141b24");
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 0);
    expect(meetsContrast("#7f7f7f")).toBe(false);
  });
});

describe("Branding", () => {
  it("previews the public page live and saves the colour", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
      "PATCH /organisations/o1": (body) => {
        sent = body;
        return { status: 200, body: { ...org, primary_colour: "#0b6e4f" } };
      },
    });
    renderApp("/internal/settings/branding");
    const preview = await screen.findByRole("figure", { name: "Preview of your public page" });
    expect(within(preview).getByText("Riverside Housing")).toBeInTheDocument();
    expect(preview.style.getPropertyValue("--pc-brand")).toBe("#1f5aa6");

    const hex = screen.getByLabelText("Hex code");
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    await userEvent.clear(hex);
    await userEvent.type(hex, "#0B6E4F");
    expect(preview.style.getPropertyValue("--pc-brand")).toBe("#0b6e4f");
    await userEvent.click(save);
    expect(await screen.findByText("Your branding has been saved.")).toBeInTheDocument();
    expect(sent).toEqual({ primary_colour: "#0b6e4f" });
  });

  it("warns when a colour is hard to read", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: org }),
    });
    renderApp("/internal/settings/branding");
    const hex = await screen.findByLabelText("Hex code");
    await userEvent.clear(hex);
    await userEvent.type(hex, "#7f7f7f");
    expect(screen.getByRole("alert")).toHaveTextContent("This colour may be hard to read.");
  });

  it("rejects something that isn't a colour", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: admin }),
      "GET /organisations/o1": () => ({ status: 200, body: { ...org, primary_colour: "#123456" } }),
    });
    renderApp("/internal/settings/branding");
    const hex = await screen.findByLabelText("Hex code");
    await userEvent.clear(hex);
    await userEvent.type(hex, "blue");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("is admin-only in the navigation and read-only for staff", async () => {
    mockApi({
      "GET /auth/me": () => ({ status: 200, body: staff }),
      "GET /organisations/o1": () => ({ status: 200, body: { ...org, role: "STAFF" } }),
    });
    renderApp("/internal/settings/branding");
    expect(await screen.findByText("#1f5aa6")).toBeInTheDocument();
    expect(screen.queryByLabelText("Hex code")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Branding" })).not.toBeInTheDocument();
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
    renderApp("/internal/settings/branding");
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
    renderApp("/internal/settings/branding");
    const logo = await screen.findByRole("region", { name: "Logo" });
    const input = within(logo).getByText("Upload logo").querySelector("input")!;
    await userEvent.upload(input, new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }), { applyAccept: false });
    expect(within(logo).getByRole("alert")).toHaveTextContent("PNG, JPEG or WebP");
  });

});
