import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth, RequireOrganisation, SETUP_PATH } from "./lib/auth";
import { CheckEmailPage } from "./pages/auth/CheckEmailPage";
import { InvitePage } from "./pages/auth/InvitePage";
import { ForgotPasswordPage } from "./pages/auth/ForgotPasswordPage";
import { LoginPage } from "./pages/auth/LoginPage";
import { ResetPasswordPage } from "./pages/auth/ResetPasswordPage";
import { SignupPage } from "./pages/auth/SignupPage";
import { VerifyEmailPage } from "./pages/auth/VerifyEmailPage";
import { InternalHomePage } from "./pages/InternalHomePage";
import { PoliciesPage } from "./pages/policies/PoliciesPage";
import { PolicyDetailPage } from "./pages/policies/PolicyDetailPage";
import { UploadPolicyPage } from "./pages/policies/UploadPolicyPage";
import { PublicOrganisationPage } from "./pages/public/PublicOrganisationPage";
import { ActivityPage } from "./pages/settings/ActivityPage";
import { MembersPage } from "./pages/settings/MembersPage";
import { OrganisationSettingsPage } from "./pages/settings/OrganisationSettingsPage";
import { CreateOrganisationPage } from "./pages/setup/CreateOrganisationPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/internal" replace />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/signup/check-email" element={<CheckEmailPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/invite" element={<InvitePage />} />
      <Route path="/p/:slug" element={<PublicOrganisationPage />} />
      <Route
        path={SETUP_PATH}
        element={
          <RequireAuth>
            <CreateOrganisationPage />
          </RequireAuth>
        }
      />
      <Route
        path="/internal"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <InternalHomePage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/settings"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <OrganisationSettingsPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/settings/members"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <MembersPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/settings/activity"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <ActivityPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/policies"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <PoliciesPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/policies/new"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <UploadPolicyPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route
        path="/internal/policies/:policyId"
        element={
          <RequireAuth>
            <RequireOrganisation>
              <PolicyDetailPage />
            </RequireOrganisation>
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
