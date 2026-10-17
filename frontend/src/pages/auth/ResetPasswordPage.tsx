import { useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, AuthLayout, Button, PasswordInput } from "../../components";
import { api, ApiError } from "../../lib/api";
import {
  focusFirstError,
  hasErrors,
  PASSWORD_MIN_LENGTH,
  validateConfirmation,
  validateNewPassword,
  type FieldErrors,
} from "../../lib/validation";

const INVALID_LINK = "This link is invalid or has expired. Please request a new one.";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const formRef = useRef<HTMLFormElement>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | undefined>(token ? undefined : INVALID_LINK);
  const [linkInvalid, setLinkInvalid] = useState(!token);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found = {
      password: validateNewPassword(password),
      confirm_password: validateConfirmation(password, confirm),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);

    setSubmitting(true);
    try {
      await api("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({ token, password, confirm_password: confirm }),
      });
      setDone(true);
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) setErrors(apiErr.fields);
      if (apiErr.code === "invalid_token") setLinkInvalid(true);
      if (apiErr.code !== "validation_error") setFormError(apiErr.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthLayout title="Password changed">
        <Alert tone="success" title="Your password has been changed." />
        <p className="pc-auth__spaced">For your security, you've been signed out on all devices.</p>
        <Link to="/login" className="pc-button pc-button--primary pc-auth__submit">
          Sign in
        </Link>
      </AuthLayout>
    );
  }

  if (linkInvalid) {
    return (
      <AuthLayout title="Reset your password">
        <Alert tone="error" title={formError ?? INVALID_LINK} />
        <Link to="/forgot-password" className="pc-button pc-button--primary pc-auth__submit pc-auth__spaced">
          Request a new link
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password">
      {formError && <Alert tone="error" title={formError} />}
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <PasswordInput
          label="Confirm new password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm_password}
        />
        <Button type="submit" loading={submitting} className="pc-auth__submit">
          Change password
        </Button>
      </form>
    </AuthLayout>
  );
}
