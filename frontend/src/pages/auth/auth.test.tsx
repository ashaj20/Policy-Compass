import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { safeNext } from "../../lib/auth";
import { mockApi, renderApp, unauthenticated } from "../../test/utils";

afterEach(() => vi.restoreAllMocks());

const user = { id: "u1", email: "jane.smith@example.org", memberships: [] };

describe("Sign up", () => {
  it("shows field errors without calling the API when the form is invalid", async () => {
    const fetchSpy = mockApi({ "GET /auth/me": () => unauthenticated });
    renderApp("/signup");
    await userEvent.type(await screen.findByLabelText("Work email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText(/Enter a valid email address/)).toBeInTheDocument();
    expect(screen.getByText(/Use at least 10 characters/)).toBeInTheDocument();
    expect(screen.getByText(/The passwords don't match/)).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1); // only the initial session check
  });

  it("submits and asks the person to check their email", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/signup": (body) => {
        sent = body;
        return { status: 201, body: { message: "ok" } };
      },
    });
    renderApp("/signup");
    await userEvent.type(await screen.findByLabelText("Work email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(user.email)).toBeInTheDocument();
    expect(sent).toEqual({
      email: user.email,
      password: "correct horse battery",
      confirm_password: "correct horse battery",
    });
  });

  it("explains when an account already exists", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/signup": () => ({
        status: 409,
        body: {
          error: {
            code: "account_exists",
            message: "An account with this email already exists. Sign in or reset your password.",
            fields: { email: "An account with this email already exists" },
          },
        },
      }),
    });
    renderApp("/signup");
    await userEvent.type(await screen.findByLabelText("Work email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByRole("link", { name: "reset your password" })).toBeInTheDocument();
  });

  it("lets people reveal the password they typed", async () => {
    mockApi({ "GET /auth/me": () => unauthenticated });
    renderApp("/signup");
    const field = await screen.findByLabelText("Password");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
  });
});

describe("Sign in", () => {
  it("redirects signed-out visitors from internal pages to sign in", async () => {
    mockApi({ "GET /auth/me": () => unauthenticated });
    renderApp("/internal");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the server's message for wrong credentials", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/login": () => ({
        status: 401,
        body: { error: { code: "invalid_credentials", message: "The email or password is incorrect." } },
      }),
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "wrong password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect.");
  });

  it("offers a new verification link when the email isn't verified", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/login": () => ({
        status: 403,
        body: { error: { code: "email_not_verified", message: "Please verify your email address." } },
      }),
      "POST /auth/resend-verification": () => ({ status: 202, body: { message: "ok" } }),
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.click(await screen.findByRole("button", { name: "Send a new link" }));
    expect(await screen.findByText(/We've sent a new verification link/)).toBeInTheDocument();
  });

  it("signs in and sends people without an organisation to setup", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/login": () => ({ status: 200, body: user }),
    });
    renderApp("/login?next=/internal");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    // A new account has no organisation yet, so it is sent to organisation setup.
    expect(await screen.findByRole("heading", { name: "Create your organisation" })).toBeInTheDocument();
  });

  it("only redirects within the app after sign in", () => {
    expect(safeNext("/internal/policies")).toBe("/internal/policies");
    expect(safeNext("//evil.example")).toBe("/internal");
    expect(safeNext("https://evil.example")).toBe("/internal");
    expect(safeNext(null)).toBe("/internal");
  });
});

describe("Email verification", () => {
  it("verifies the token once and offers sign in", async () => {
    const fetchSpy = mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/verify-email": () => ({ status: 200, body: { message: "ok" } }),
    });
    renderApp("/verify-email?token=abc");
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    const verifyCalls = fetchSpy.mock.calls.filter(([url]) => String(url).includes("verify-email"));
    expect(verifyCalls).toHaveLength(1);
  });

  it("explains an expired link and lets people request a new one", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/verify-email": () => ({
        status: 400,
        body: { error: { code: "invalid_token", message: "This link is invalid or has expired. Please request a new one." } },
      }),
      "POST /auth/resend-verification": () => ({ status: 202, body: { message: "ok" } }),
    });
    renderApp("/verify-email?token=old");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    await userEvent.type(screen.getByLabelText("Your email address"), user.email);
    await userEvent.click(screen.getByRole("button", { name: "Send a new verification link" }));
    expect(await screen.findByText(/we've sent a new link/)).toBeInTheDocument();
  });
});

describe("Password reset", () => {
  it("confirms the request without revealing whether the account exists", async () => {
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/password-reset/request": () => ({ status: 202, body: { message: "ok" } }),
    });
    renderApp("/forgot-password");
    await userEvent.type(await screen.findByLabelText("Email"), user.email);
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If an account exists for/)).toBeInTheDocument();
  });

  it("changes the password with a valid link", async () => {
    let sent: unknown;
    mockApi({
      "GET /auth/me": () => unauthenticated,
      "POST /auth/password-reset/confirm": (body) => {
        sent = body;
        return { status: 200, body: { message: "ok" } };
      },
    });
    renderApp("/reset-password?token=tok123");
    await userEvent.type(await screen.findByLabelText("New password"), "a brand new passphrase");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "a brand new passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeInTheDocument();
    expect(sent).toMatchObject({ token: "tok123" });
  });

  it("explains a missing or invalid link", async () => {
    mockApi({ "GET /auth/me": () => unauthenticated });
    renderApp("/reset-password");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("Signed-in visitors", () => {
  it("are sent straight on from the sign-in page", async () => {
    mockApi({ "GET /auth/me": () => ({ status: 200, body: user }) });
    renderApp("/login");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Create your organisation" })).toBeInTheDocument(),
    );
  });
});
