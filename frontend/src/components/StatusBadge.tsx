import { STATUS_LABELS, type VersionStatus } from "../lib/policy";

const ICONS: Record<VersionStatus, string> = {
  PROCESSING: "◐",
  DRAFT: "○",
  READY: "◷",
  ACTIVE: "✓",
  SUPERSEDED: "↺",
  FAILED: "✕",
  ARCHIVED: "▣",
};

/** Policy/version status. Text and icon carry the meaning; colour only reinforces it. */
export function StatusBadge({ status }: { status: VersionStatus }) {
  return (
    <span className={`pc-badge pc-status-badge pc-status-badge--${status.toLowerCase()}`}>
      <span aria-hidden="true">{ICONS[status]}</span> {STATUS_LABELS[status]}
    </span>
  );
}
