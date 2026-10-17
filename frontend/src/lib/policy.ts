/** Policy types and the upload rules (mirrors backend/app/policies/validation.py). */

export type Audience = "INTERNAL" | "PUBLIC" | "BOTH";
export type VersionStatus = "DRAFT" | "PROCESSING" | "READY" | "SUPERSEDED" | "ARCHIVED" | "FAILED";

export interface PolicyVersion {
  id: string;
  version: string;
  effective_date: string;
  status: VersionStatus;
  original_filename: string;
  file_size: number;
  uploaded_at: string;
  uploaded_by: string | null;
}

export interface Policy {
  id: string;
  name: string;
  category: string;
  audience: Audience;
  source: string | null;
  created_at: string;
  updated_at: string;
  latest_version: PolicyVersion;
}

export const AUDIENCE_OPTIONS: { value: Audience; label: string; description: string }[] = [
  { value: "INTERNAL", label: "Internal", description: "Staff only. Never shown to the public." },
  { value: "PUBLIC", label: "Public", description: "Can be used to answer public questions." },
  { value: "BOTH", label: "Both", description: "Staff and the public." },
];

export const POLICY_FILE_ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const POLICY_MAX_BYTES = 20 * 1024 * 1024;

export function validatePolicyFile(file: File): string | undefined {
  const ext = file.name.toLowerCase().split(".").pop();
  if (ext !== "pdf" && ext !== "docx") return "This file type isn't supported. Upload a PDF or Word (.docx) document.";
  if (file.size === 0) return "The file is empty. Choose a PDF or Word document.";
  if (file.size > POLICY_MAX_BYTES) return "The file must be 20 MB or smaller.";
}

export function validatePolicyName(v: string): string | undefined {
  const t = v.trim();
  if (!t) return "Enter the policy name";
  if (t.length > 200) return "Use no more than 200 characters";
}

export function validateVersion(v: string): string | undefined {
  const t = v.trim();
  if (!t) return "Enter the version, for example 2.1";
  if (t.length > 20) return "Use no more than 20 characters";
  if (!/^[0-9A-Za-z][0-9A-Za-z.-]*$/.test(t)) return "Use letters, numbers, dots and hyphens only, for example 2.1";
}

export function validateEffectiveDate(v: string): string | undefined {
  if (!v) return "Enter the date this version takes effect";
  const year = Number(v.slice(0, 4));
  if (!Number.isFinite(year) || year < 1990 || year > 2100) return "Enter a real effective date";
}

export function validateCategory(v: string): string | undefined {
  const t = v.trim();
  if (!t) return "Enter a category, for example Repairs";
  if (t.length > 60) return "Use no more than 60 characters";
}

/** Suggest a policy name from a file name: "emergency_repairs-policy v3.pdf" -> "Emergency repairs policy v3". */
export function nameFromFilename(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return base ? base.charAt(0).toUpperCase() + base.slice(1) : "";
}
