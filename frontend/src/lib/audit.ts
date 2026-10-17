/** Turning audit events into plain-English sentences for the activity view (US-005A). */

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  object_label: string | null;
  previous: Record<string, unknown> | null;
  new: Record<string, unknown> | null;
}

export interface AuditDescription {
  /** What happened, after the actor's name, e.g. "invited john@example.org as a staff member". */
  summary: string;
  /** Before → after lines for changed values. */
  changes: { label: string; from: string; to: string }[];
}

const ROLE: Record<string, string> = { ADMIN: "Administrator", STAFF: "Staff member" };
const FIELD: Record<string, string> = {
  name: "Name",
  website: "Website",
  slug: "Public URL",
  logo: "Logo",
  role: "Role",
  category: "Category",
  audience: "Audience",
  source: "Source",
};
const AUDIENCE: Record<string, string> = { INTERNAL: "Internal", PUBLIC: "Public", BOTH: "Both" };

function show(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not set";
  if (field === "role") return ROLE[String(value)] ?? String(value);
  if (field === "audience") return AUDIENCE[String(value)] ?? String(value);
  if (field === "slug") return `/p/${value}`;
  return String(value);
}

function diff(e: AuditEvent): AuditDescription["changes"] {
  const keys = new Set([...Object.keys(e.previous ?? {}), ...Object.keys(e.new ?? {})]);
  return [...keys].map((k) => ({
    label: FIELD[k] ?? k,
    from: show(k, e.previous?.[k]),
    to: show(k, e.new?.[k]),
  }));
}

export function describeEvent(e: AuditEvent): AuditDescription {
  const who = e.object_label ?? "a member";
  const role = (v: unknown) => (ROLE[String(v)] ?? String(v)).toLowerCase();
  switch (e.action) {
    case "ORGANISATION_CREATED":
      return { summary: `created the organisation ${e.object_label}`, changes: [] };
    case "ORGANISATION_SETTINGS_CHANGED":
      return { summary: "changed the organisation details", changes: diff(e) };
    case "PUBLIC_URL_CHANGED":
      return { summary: "changed the public URL", changes: diff(e) };
    case "LOGO_UPDATED":
      return { summary: "uploaded a new logo", changes: [] };
    case "LOGO_REMOVED":
      return { summary: "removed the logo", changes: [] };
    case "MEMBER_INVITED":
      return { summary: `invited ${who} as ${aOrAn(role(e.new?.role))}`, changes: [] };
    case "INVITATION_RESENT":
      return { summary: `resent the invitation to ${who}`, changes: [] };
    case "INVITATION_CANCELLED":
      return { summary: `cancelled the invitation to ${who}`, changes: [] };
    case "MEMBER_JOINED":
      return { summary: `joined as ${aOrAn(role(e.new?.role))}`, changes: [] };
    case "MEMBER_ROLE_CHANGED":
      return { summary: `changed the role of ${who}`, changes: diff(e) };
    case "MEMBER_REMOVED":
      return { summary: `removed ${who} from the organisation`, changes: [] };
    case "POLICY_UPLOADED":
      return {
        summary: `uploaded the policy ${e.object_label}${e.new?.version ? ` (version ${e.new.version})` : ""}`,
        changes: [],
      };
    case "POLICY_EDITED":
      return { summary: `edited the policy ${e.object_label}`, changes: diff(e) };
    default:
      return { summary: e.action.toLowerCase().replace(/_/g, " "), changes: diff(e) };
  }
}

function aOrAn(noun: string): string {
  return /^[aeiou]/i.test(noun) ? `an ${noun}` : `a ${noun}`;
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
