import { formatLongDate, formatRelativeDay } from "../lib/format";

interface VersionMetaProps {
  version: string;
  effectiveDate: string;
  updatedAt?: string;
}

/** "Version 2.1 · Effective 01 September 2026 · Last updated today" (US-008). */
export function VersionMeta({ version, effectiveDate, updatedAt }: VersionMetaProps) {
  return (
    <p className="pc-version-meta">
      <span>Version {version}</span>
      <span aria-hidden="true"> · </span>
      <span>Effective {formatLongDate(effectiveDate)}</span>
      {updatedAt && (
        <>
          <span aria-hidden="true"> · </span>
          <span>
            Last updated <time dateTime={updatedAt}>{formatRelativeDay(updatedAt)}</time>
          </span>
        </>
      )}
    </p>
  );
}