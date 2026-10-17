import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, AuthLayout, Button, LoadingState, PasswordInput } from "../../components";
import { api, ApiError } from "../../lib/api";
import { useAuth, type User } from "../../lib/auth";
import {
  focusFirstError,
  hasErrors,
  PASSWORD_MIN_LENGTH,
  validateConfirmation,
  validateNewPassword,
  type FieldErrors,
} from "../../lib/validation";

interface InvitationDetails {
  organisation_name: string;
  email: string;
  role: "ADMIN" | "STAFF";
  account_exists: boolean;
}

const ROLE_LABEL = { ADMIN: "an administrator", STAFF: "a staff member" } as const;
const INVALID = "This invitation is invalid or has expired. Ask your administrator to send a new one.";

/** Accept an organisation invitation from the emailed link (US-003). */
export function InvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { user, loading, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [details, setDetails] = useState<InvitationDetails>();
  const [error, setError] = useState<string | undefined>(token ? undefined : INVALID);
  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState<string>();

  useEffect(() => {
    if (!token) return;
    api<InvitationDetails>("/invitations/lookup", { method: "POST", body: JSON.stringify({ token }) })
      .then(setDetails)
      .catch((err: ApiError) => setError(err.message));
  }, [token]);

  if (error) {
    return (
      <AuthLayout title="Invitation unavailable">
        <Alert tone="error" title={error} />
        <p className="pc-auth__spaced">
          <Link to="/login">Go to sign in</Link>
        </p>
      </AuthLayout>
    );
  }
  if (!details || loading) {
    return (
      <AuthLayout title="Your invitation">
        <LoadingState label="Checking your invitation…" />
      </AuthLayout>
    );
  }

  const intro = (
    <p>
      You've been invited to join <strong>{details.organisation_name}</strong> on Policy Compass as{" "}
      {ROLE_LABEL[details.role]}.
    </p>
  );

  async function acceptSignedIn() {
    setAccepting(true);
    setAcceptError(undefined);
    try {
      setUser(await api<User>("/invitations/accept", { method: "POST", body: JSON.stringify({ token }) }));
      navigate("/internal", { replace: true });
    } catch (err) {
      setAcceptError((err as ApiError).message);
      setAccepting(false);
    }
  }

  // Signed in as the invited person: one click to accept.
  if (user && user.email === details.email) {
    return (
      <AuthLayout title="Join your organisation">
        {intro}
        {acceptError && <Alert tone="error" title={acceptError} />}
        <Button onClick={acceptSignedIn} loading={accepting} className="pc-auth__submit">
          Accept invitation
        </Button>
      </AuthLayout>
    );
  }

  // Signed in as someone else.
  if (user) {
    return (
      <AuthLayout title="Join your organisation">
        {intro}
        <Alert tone="warning" title={`This invitation was sent to ${details.email}.`}>
          <p>You're signed in as {user.email}. Sign out, then sign in with the invited address.</p>
        </Alert>
        <Button variant="secondary" onClick={() => logout()} className="pc-auth__submit">
          Sign out
        </Button>
      </AuthLayout>
    );
  }

  // Not signed in, account exists: sign in first and come back here.
  if (details.account_exists) {
    const next = encodeURIComponent(`/invite?token=${token}`);
    return (
      <AuthLayout title="Join your organisation">
        {intro}
        <p className="pc-auth__muted">Sign in as {details.email} to accept.</p>
        <Link to={`/login?next=${next}`} className="pc-button pc-button--primary pc-auth__submit">
          Sign in to accept
        </Link>
      </AuthLayout>
    );
  }

  return <CreateAccountFromInvite token={token} details={details} intro={intro} />;
}

function CreateAccountFromInvite({
  token,
  details,
  intro,
}: {
  token: string;
  details: InvitationDetails;
  intro: ReactNode;
}) {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found = {
      password: validateNewPassword(password, details.email),
      confirm_password: validateConfirmation(password, confirm),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    setBusy(true);
    try {
      const user = await api<User>("/invitations/accept-new", {
        method: "POST",
        body: JSON.stringify({ token, password, confirm_password: confirm }),
      });
      setUser(user);
      navigate("/internal", { replace: true });
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) setErrors(apiErr.fields);
      if (apiErr.code !== "validation_error") setFormError(apiErr.message);
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Join your organisation">
      {intro}
      <p className="pc-auth__muted">
        Choose a password to create your account for <strong>{details.email}</strong>.
      </p>
      {formError && <Alert tone="error" title={formError} />}
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <PasswordInput
          label="Password"
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
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
        <Button type="submit" loading={busy} className="pc-auth__submit">
          Create account and join
        </Button>
      </form>
    </AuthLayout>
  );
}
