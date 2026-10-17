import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, AuthLayout, Button, Input, LoadingState } from "../../components";
import { api, ApiError } from "../../lib/api";
import { validateEmail } from "../../lib/validation";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"verifying" | "verified" | "failed">(token ? "verifying" : "failed");
  const [message, setMessage] = useState("This link is invalid or has expired. Please request a new one.");
  const started = useRef(false);

  useEffect(() => {
    // Tokens are single use; guard against React running the effect twice in development.
    if (!token || started.current) return;
    started.current = true;
    api("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) })
      .then(() => setState("verified"))
      .catch((err: ApiError) => {
        setMessage(err.message);
        setState("failed");
      });
  }, [token]);

  if (state === "verifying") {
    return (
      <AuthLayout title="Verifying your email">
        <LoadingState label="Verifying your email address…" />
      </AuthLayout>
    );
  }

  if (state === "verified") {
    return (
      <AuthLayout title="Email verified">
        <Alert tone="success" title="Your email address is verified." />
        <p className="pc-auth__spaced">You can now sign in to Policy Compass.</p>
        <Link to="/login" className="pc-button pc-button--primary pc-auth__submit">
          Sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="We couldn't verify your email"
      footer={
        <p>
          <Link to="/login">Back to sign in</Link>
        </p>
      }
    >
      <Alert tone="error" title={message} />
      <RequestNewLink />
    </AuthLayout>
  );
}

function RequestNewLink() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string>();
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validateEmail(email);
    setError(problem);
    if (problem) return;
    setState("sending");
    try {
      await api("/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }) });
      setState("sent");
    } catch (err) {
      setError((err as ApiError).message);
      setState("idle");
    }
  }

  if (state === "sent") {
    return (
      <Alert tone="success" title="If that account still needs verifying, we've sent a new link." />
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="pc-auth__form pc-auth__spaced">
      <Input
        label="Your email address"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={error}
      />
      <Button type="submit" variant="secondary" loading={state === "sending"}>
        Send a new verification link
      </Button>
    </form>
  );
}