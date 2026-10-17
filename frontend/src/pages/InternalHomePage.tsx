import { Link, useLocation } from "react-router-dom";
import { Alert, AppShell, PageHeader } from "../components";
import { currentMembership, useAuth } from "../lib/auth";

const ROLE_LABELS = { ADMIN: "Administrator", STAFF: "Staff member" } as const;

/**
 * Temporary signed-in home until the dashboard (US-021). Shows the organisation the person
 * belongs to and its public page.
 */
export function InternalHomePage() {
  const { user } = useAuth();
  const state = useLocation().state as { created?: boolean; notice?: string } | null;
  const membership = currentMembership(user)!;

  return (
    <AppShell>
      <PageHeader title={membership.organisation_name} description="Welcome to Policy Compass." />
      {state?.created && <Alert tone="success" title="Your organisation has been created." />}
      {state?.notice && <Alert tone="warning" title={state.notice} />}
      <section className="pc-card">
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
        <p className="pc-auth__muted pc-auth__spaced">
          The dashboard and policy tools will appear here as they're built.
        </p>
        {membership.role === "ADMIN" && (
          <Link to="/internal/policies/new" className="pc-button pc-button--primary">
            Upload a policy
          </Link>
        )}
      </section>
    </AppShell>
  );
}
