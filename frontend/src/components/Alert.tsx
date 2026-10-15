import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "error";

const ICONS: Record<Tone, string> = { info: "ℹ", success: "✓", warning: "!", error: "⚠" };

interface AlertProps {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  actions?: ReactNode;
}

/** Errors and warnings are announced immediately (role=alert); others politely (role=status). */
export function Alert({ tone = "info", title, children, actions }: AlertProps) {
  const role = tone === "error" || tone === "warning" ? "alert" : "status";
  return (
    <div className={`pc-alert pc-alert--${tone}`} role={role}>
      <span className="pc-alert__icon" aria-hidden="true">
        {ICONS[tone]}
      </span>
      <div className="pc-alert__body">
        {title && <p className="pc-alert__title">{title}</p>}
        {children && <div className="pc-alert__text">{children}</div>}
        {actions && <div className="pc-alert__actions">{actions}</div>}
      </div>
    </div>
  );
}
