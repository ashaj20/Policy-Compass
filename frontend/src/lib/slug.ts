/** Public URL slugs. Mirrors backend/app/organisations/validation.py; the API has the final say. */

export const SLUG_MAX = 50;

/** Suggest a slug from an organisation name: "Riverside Housing & Care" -> "riverside-housing-and-care". */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, SLUG_MAX)
    .replace(/-+$/g, "");
}

export function validateSlug(value: string): string | undefined {
  if (!value) return "Enter a public URL";
  if (value !== value.toLowerCase()) return "Use lowercase letters only";
  if (value.length < 3) return "Use at least 3 characters";
  if (value.length > SLUG_MAX) return `Use no more than ${SLUG_MAX} characters`;
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(value)) {
    return "Use only lowercase letters, numbers and single hyphens, with no spaces and no hyphen at the start or end";
  }
}

export function publicUrl(slug: string): string {
  return `${window.location.origin}/p/${slug}`;
}
