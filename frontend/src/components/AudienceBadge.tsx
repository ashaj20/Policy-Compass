import type { Audience } from "../lib/policy";

const BADGES: Record<Audience, { label: string; icon: string; description: string }> = {
  INTERNAL: { label: "Internal", icon: "🔒", description: "Staff only" },
  PUBLIC: { label: "Public", icon: "🌐", description: "Staff and the public" },
  BOTH: { label: "Both", icon: "⇄", description: "Staff and the public" },
};

/** Who a policy is for. Always shown as text plus an icon, never colour alone. */
export function AudienceBadge({ audience }: { audience: Audience }) {
  const b = BADGES[audience];
  return (
    <span className={`pc-badge pc-badge--${audience.toLowerCase()}`} title={b.description}>
      <span aria-hidden="true">{b.icon}</span> {b.label}
      <span className="visually-hidden"> audience: {b.description.toLowerCase()}</span>
    </span>
  );
}
