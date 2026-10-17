import { useNavigate } from "react-router-dom";
import { Alert, AuthLayout, Button } from "../components";
import { useAuth } from "../lib/auth";

/**
 * Temporary signed-in page. A new account has no organisation access until a membership exists;
 * US-002 replaces this with organisation setup and US-021 with the dashboard.
 */
export function InternalHomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function onSignOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AuthLayout title="You're signed in">
      <p>
        Signed in as <strong>{user?.email}</strong>.
      </p>
      <Alert tone="info" title="You're not part of an organisation yet.">
        <p>Organisation setup is the next step and will appear here soon.</p>
      </Alert>
      <Button variant="secondary" onClick={onSignOut} className="pc-auth__submit pc-auth__spaced">
        Sign out
      </Button>
    </AuthLayout>
  );
}
