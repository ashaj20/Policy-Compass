import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, AuthLayout, Button, Input, PasswordInput } from "../../components";
import { api, ApiError } from "../../lib/api";
import {
  focusFirstError,
  hasErrors,
  PASSWORD_MIN_LENGTH,
  validateConfirmation,
  validateEmail,
  validateNewPassword,
  type FieldErrors,
} from "../../lib/validation";

export function SignupPage() {
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found = {
      email: validateEmail(email),
      password: validateNewPassword(password, email),
      confirm_password: validateConfirmation(password, confirm),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);

    setSubmitting(true);
    try {
      await api("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, confirm_password: confirm }),
      });
      navigate("/signup/check-email", { state: { email: email.trim() } });
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) {
        setErrors(apiErr.fields);
        focusFirstError(formRef.current);
      }
      if (apiErr.code !== "validation_error") setFormError(apiErr.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Turn policies into clear answers."
      footer={
        <p>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      }
    >
      {formError && (
        <Alert tone="error" title={formError}>
          {formError.includes("already exists") && (
            <p>
              <Link to="/login">Sign in</Link> or <Link to="/forgot-password">reset your password</Link>.
            </p>
          )}
        </Alert>
      )}
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <Input
          label="Work email"
          type="email"
          autoComplete="email"
          placeholder="name@organisation.org"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordInput
          label="Password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN_LENGTH} characters. A short phrase works well.`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <PasswordInput
          label="Confirm password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm_password}
        />
        <Button type="submit" loading={submitting} className="pc-auth__submit">
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
