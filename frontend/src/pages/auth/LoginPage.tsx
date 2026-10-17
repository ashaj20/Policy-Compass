import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, AuthLayout, Button, Input, PasswordInput } from "../../components";
import { api, ApiError } from "../../lib/api";
import { safeNext, useAuth, type User } from "../../lib/auth";
import { focusFirstError, hasErrors, validateEmail, type FieldErrors } from "../../lib/validation";
import { ResendVerification } from "./ResendVerification";

export function LoginPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<ApiError>();
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={next} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFailure(undefined);
    const found = {
      email: validateEmail(email),
      password: password ? undefined : "Enter your password",
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);

    setSubmitting(true);
    try {
      const signedIn = await api<User>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUser(signedIn);
      navigate(next, { replace: true });
    } catch (err) {
      setFailure(err as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back to Policy Compass."
      footer={
        <p>
          New to Policy Compass? <Link to="/signup">Create an account</Link>
        </p>
      }
    >
      {failure?.code === "email_not_verified" ? (
        <Alert tone="warning" title="Verify your email address" actions={<ResendVerification email={email.trim()} />}>
          <p>{failure.message}</p>
        </Alert>
      ) : (
        failure && <Alert tone="error" title={failure.message} />
      )}
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <p className="pc-auth__inline-link">
          <Link to="/forgot-password">Forgot your password?</Link>
        </p>
        <Button type="submit" loading={submitting} className="pc-auth__submit">
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}
