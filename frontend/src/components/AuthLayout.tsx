import type { ReactNode } from "react";

/** Policy Compass mark: a compass needle over a document. Decorative; the name is shown beside it. */
export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect x="6" y="3" width="28" height="34" rx="4" fill="var(--pc-primary-50)" stroke="var(--pc-brand)" strokeWidth="2" />
      <circle cx="20" cy="20" r="10" fill="none" stroke="var(--pc-brand)" strokeWidth="2" />
      <path d="M20 12 L23 20 L20 28 L17 20 Z" fill="var(--pc-brand)" />
      <circle cx="20" cy="20" r="1.6" fill="#fff" />
    </svg>
  );
}

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Centred card used by signup, sign-in, verification and password reset screens. */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <main className="pc-auth">
      <div className="pc-auth__brand">
        <Logo />
        <span className="pc-auth__product">Policy Compass</span>
      </div>
      <section className="pc-auth__card" aria-labelledby="pc-auth-title">
        <h1 id="pc-auth-title" className="pc-auth__title">
          {title}
        </h1>
        {subtitle && <p className="pc-auth__subtitle">{subtitle}</p>}
        {children}
      </section>
      {footer && <div className="pc-auth__footer">{footer}</div>}
    </main>
  );
}
