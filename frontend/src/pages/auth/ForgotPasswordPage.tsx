import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Alert, AuthLayout, Button, Input } from "../../components";
import { api, ApiError } from "../../lib/api";
import { focusFirstError, validateEmail } from "../../lib/validation";

export function ForgotPasswordPage() {
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const problem = validateEmail(email);
    setError(problem);
    if (problem) return focusFirstError(formRef.current);

    setSubmitting(true);
    try {
      await api("/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    } catch (err) {
      setFormError((err as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  }

  const footer = (
    <p>
      <Link to="/login">Back to sign in</Link>
    </p>
  );

  if (sent) {
    return (
      <AuthLayout title="Check your email" footer={footer}>
        <p>
          If an account exists for <strong>{email.trim()}</strong>, we've sent a link to reset the
          password. The link expires in 60 minutes.
        </p>
        {import.meta.env.DEV && (
          <p className="pc-auth__dev-note">
            Development: emails aren't sent. The link is printed in the terminal running the API.
          </p>
        )}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link to choose a new password."
      footer={footer}
    >
      {formError && <Alert tone="error" title={formError} />}
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={error}
        />
        <Button type="submit" loading={submitting} className="pc-auth__submit">
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  );
}
