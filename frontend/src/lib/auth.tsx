import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingState } from "../components";
import { api } from "./api";

export interface Membership {
  organisation_id: string;
  organisation_name: string;
  organisation_slug: string;
  role: "ADMIN" | "STAFF";
}

export interface User {
  id: string;
  email: string;
  memberships: Membership[];
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  /** Reload the signed-in user, e.g. after joining or creating an organisation. */
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, setUser, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** The organisation the user is working in. Beta: one organisation per person. */
export function currentMembership(user: User | null): Membership | undefined {
  return user?.memberships[0];
}

export const SETUP_PATH = "/internal/setup/organisation";

/** Sends signed-out visitors to the sign-in page, remembering where they were going. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState label="Loading…" />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Internal pages need an organisation; people without one are sent to set one up. */
export function RequireOrganisation({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!currentMembership(user)) return <Navigate to={SETUP_PATH} replace />;
  return <>{children}</>;
}

/** Only allow redirects to paths inside this app (never "//other-site" or full URLs). */
export function safeNext(next: string | null, fallback = "/internal"): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}
