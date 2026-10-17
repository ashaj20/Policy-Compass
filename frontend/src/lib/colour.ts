/** Brand colour helpers. Mirror backend/app/organisations/validation.py (the API decides). */

export const DEFAULT_BRAND = "#1f5aa6";
const DARK_TEXT = "#141b24";
const LIGHT_TEXT = "#ffffff";

/** "#1F5AA6", "1f5aa6" or "f60" -> "#1f5aa6" / "#ff6600"; undefined if not a hex colour. */
export function normaliseHex(value: string): string | undefined {
  const m = value.trim().match(/^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/);
  if (!m) return;
  const digits = m[1].length === 3 ? m[1].split("").map((c) => c + c).join("") : m[1];
  return `#${digits.toLowerCase()}`;
}

function luminance(hex: string): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function textColourFor(background: string): string {
  return contrastRatio(background, LIGHT_TEXT) >= contrastRatio(background, DARK_TEXT) ? LIGHT_TEXT : DARK_TEXT;
}

export function meetsContrast(background: string): boolean {
  return contrastRatio(background, textColourFor(background)) >= 4.5;
}

/** A slightly darker shade for hover states. */
export function darken(hex: string, amount = 0.15): string {
  const parts = [1, 3, 5].map((i) => Math.round(parseInt(hex.slice(i, i + 2), 16) * (1 - amount)));
  return `#${parts.map((p) => p.toString(16).padStart(2, "0")).join("")}`;
}

/** CSS custom properties that apply a brand colour to everything inside an element. */
export function brandStyle(colour: string, text?: string): Record<string, string> {
  return {
    "--pc-brand": colour,
    "--pc-brand-strong": darken(colour),
    "--pc-brand-contrast": text ?? textColourFor(colour),
  };
}