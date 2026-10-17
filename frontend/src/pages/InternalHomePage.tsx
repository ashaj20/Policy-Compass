import { Link, useLocation, useNavigate } from "react-router-dom";
import { Alert, AuthLayout, Button } from "../components";
import { currentMembership, useAuth } from "../lib/auth";

const ROLE_LABELS = { ADMIN: "Administrator", STAFF: "Staff member" } as const;

/**
 * Temporary signed-in home until the dashboard (US-021). Shows the organisation the person
 * belongs to and its public page.
 */
export function InternalHomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const state = useLocation().state as { created?: boolean; notice?: string } | null;
  const membership = currentMembership(user)!;

  async function onSignOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AuthLayout title={membership.organisation_name}>
      {state?.created && <Alert tone="success" title="Your organisation has been created." />}
      {state?.notice && <Alert tone="warning" title={state.notice} />}
      <dl className="pc-summary">
        <div>
          <dt>Signed in as</dt>
          <dd>{user?.email}</dd>
        </div>
        <div>
          <dt>Your role</dt>
          <dd>{ROLE_LABELS[membership.role]}</dd>
        </div>
        <div>
          <dt>Public page</dt>
          <dd>
            <Link to={`/p/${membership.organisation_slug}`}>/p/{membership.organisation_slug}</Link>
          </dd>
        </div>
      </dl>
      <p className="pc-auth__muted">The dashboard and policy tools will appear here as they're built.</p>
      <Button variant="secondary" onClick={onSignOut} className="pc-auth__submit">
        Sign out
      </Button>
    </AuthLayout>
  );
}
