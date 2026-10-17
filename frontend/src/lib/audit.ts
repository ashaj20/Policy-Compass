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
  active_version: "Active version",
  owner: "Policy owner",
  help_route: "Public help route",
  job_title: "Job title",
  email: "Email",
  phone: "Phone",
  label: "Label",
  destination: "Destination",
  description: "Description",
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
    case "POLICY_ARCHIVED":
      return { summary: `archived the policy ${e.object_label}`, changes: [] };
    case "POLICY_RESTORED":
      return { summary: `restored the policy ${e.object_label}`, changes: [] };
    case "POLICY_VERSION_CREATED":
      return { summary: `uploaded version ${e.new?.version} of ${e.object_label}`, changes: [] };
    case "POLICY_VERSION_REPLACED":
      return {
        summary: `replaced unpublished version ${e.previous?.version} of ${e.object_label} with version ${e.new?.version}`,
        changes: [],
      };
    case "POLICY_VERSION_SUBMITTED":
      return { summary: `marked version ${e.new?.version} of ${e.object_label} ready for approval`, changes: [] };
    case "POLICY_VERSION_WITHDRAWN":
      return { summary: `withdrew version ${e.previous?.version} of ${e.object_label} back to draft`, changes: [] };
    case "POLICY_VERSION_REJECTED":
      return {
        summary: `sent version ${e.previous?.version} of ${e.object_label} back to draft: “${e.new?.reason}”`,
        changes: [],
      };
    case "POLICY_ACTIVATED":
      return { summary: `approved and activated ${e.object_label}`, changes: diff(e) };
    case "POLICY_SUPERSEDED":
      return { summary: `superseded version ${e.previous?.version} of ${e.object_label}`, changes: [] };
    case "POLICY_PROCESSING_RETRIED":
      return { summary: `retried processing version ${e.previous?.version} of ${e.object_label}`, changes: [] };
    case "POLICY_OWNER_CHANGED":
      return { summary: `changed the policy owner of ${e.object_label}`, changes: diff(e) };
    case "PUBLIC_HELP_ROUTE_CHANGED":
      return { summary: `changed the public help route of ${e.object_label}`, changes: diff(e) };
    case "CONTACT_CREATED":
      return { summary: `added the policy owner ${e.object_label}`, changes: [] };
    case "CONTACT_UPDATED":
      return { summary: `updated the policy owner ${e.object_label}`, changes: diff(e) };
    case "CONTACT_DELETED":
      return { summary: `removed the policy owner ${e.object_label}`, changes: [] };
    case "HELP_ROUTE_CREATED":
      return { summary: `added the public help route ${e.object_label}`, changes: [] };
    case "HELP_ROUTE_UPDATED":
      return { summary: `updated the public help route ${e.object_label}`, changes: diff(e) };
    case "HELP_ROUTE_DELETED":
      return { summary: `removed the public help route ${e.object_label}`, changes: [] };
    case "DEFAULT_HELP_ROUTE_CHANGED":
      return { summary: `made ${e.object_label} the default public help route`, changes: [] };
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
