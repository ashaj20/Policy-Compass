import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { currentMembership, useAuth } from "../lib/auth";
import { Logo } from "./AuthLayout";

interface NavItem {
  to: string;
  label: string;
  adminOnly?: boolean;
  end?: boolean;
}

interface NavGroup {
  label?: string;
  items: NavItem[];
}

// Only pages that exist are listed; the navigation grows as stories are built (Spec §27).
const NAV: NavGroup[] = [
  { items: [{ to: "/internal", label: "Home", end: true }] },
  {
    label: "Settings",
    items: [
      { to: "/internal/settings", label: "Organisation", end: true },
      { to: "/internal/settings/members", label: "Members", adminOnly: true },
    ],
  },
];

/** Internal application layout: sidebar navigation, top bar and main content area. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const membership = currentMembership(user);
  const isAdmin = membership?.role === "ADMIN";
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile menu after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  async function onSignOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((i) => isAdmin || !i.adminOnly) })).filter(
    (g) => g.items.length > 0,
  );

  return (
    <div className="pc-shell">
      <a href="#main" className="pc-skip-link">
        Skip to main content
      </a>
      <header className="pc-topbar">
        <button
          type="button"
          className="pc-topbar__menu"
          aria-expanded={menuOpen}
          aria-controls="pc-sidebar"
          onClick={() => setMenuOpen((o) => !o)}
        >
          <span aria-hidden="true">☰</span> Menu
        </button>
        <div className="pc-topbar__brand">
          <Logo size={28} />
          <span>Policy Compass</span>
        </div>
        <div className="pc-topbar__org">{membership?.organisation_name}</div>
        <div className="pc-topbar__user">
          <span className="pc-topbar__email">{user?.email}</span>
          <button type="button" className="pc-button pc-button--ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>
      <div className="pc-shell__body">
        <nav id="pc-sidebar" className={`pc-sidebar ${menuOpen ? "pc-sidebar--open" : ""}`} aria-label="Main">
          {groups.map((group, i) => (
            <div key={group.label ?? i} className="pc-sidebar__group">
              {group.label && <p className="pc-sidebar__heading">{group.label}</p>}
              <ul>
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink to={item.to} end={item.end} className="pc-sidebar__link">
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <main id="main" className="pc-main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="pc-page-header">
      <div>
        <h1 className="pc-page-header__title">{title}</h1>
        {description && <p className="pc-page-header__description">{description}</p>}
      </div>
      {actions && <div className="pc-page-header__actions">{actions}</div>}
    </div>
  );
}
