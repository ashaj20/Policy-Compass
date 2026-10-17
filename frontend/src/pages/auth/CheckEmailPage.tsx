import { Link, Navigate, useLocation } from "react-router-dom";
import { AuthLayout } from "../../components";
import { ResendVerification } from "./ResendVerification";

export function CheckEmailPage() {
  const email = (useLocation().state as { email?: string } | null)?.email;
  if (!email) return <Navigate to="/signup" replace />;

  return (
    <AuthLayout
      title="Check your email"
      footer={
        <p>
          <Link to="/login">Back to sign in</Link>
        </p>
      }
    >
      <p>
        We've sent a verification link to <strong>{email}</strong>. Open it to finish creating your
        account. The link expires in 24 hours.
      </p>
      {import.meta.env.DEV && (
        <p className="pc-auth__dev-note">
          Development: emails aren't sent. The link is printed in the terminal running the API.
        </p>
      )}
      <p className="pc-auth__muted">Didn't get it? Check your spam folder, or:</p>
      <ResendVerification email={email} />
    </AuthLayout>
  );
}
