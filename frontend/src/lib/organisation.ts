/** Organisation field rules shared by setup and settings. The API re-checks everything. */

export interface Organisation {
  id: string;
  name: string;
  slug: string;
  website: string | null;
  logo_url: string | null;
  role: "ADMIN" | "STAFF";
}

export const LOGO_MAX_BYTES = 2 * 1024 * 1024;
export const LOGO_ACCEPT = "image/png,image/jpeg,image/webp";

export function validateLogo(file: File): string | undefined {
  if (!LOGO_ACCEPT.split(",").includes(file.type)) return "The logo must be a PNG, JPEG or WebP image.";
  if (file.size > LOGO_MAX_BYTES) return "The logo must be 2 MB or smaller.";
}

export function validateOrganisationName(value: string): string | undefined {
  const v = value.trim();
  if (!v) return "Enter your organisation's name";
  if (v.length < 2) return "Use at least 2 characters";
  if (v.length > 100) return "Use no more than 100 characters";
}

export function validateWebsite(value: string): string | undefined {
  const v = value.trim();
  if (!v) return;
  const withScheme = v.includes("://") ? v : `https://${v}`;
  try {
    const url = new URL(withScheme);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".") || v.includes(" ")) {
      throw new Error();
    }
  } catch {
    return "Enter a valid website address, like https://www.organisation.org";
  }
}
