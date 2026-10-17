/** Contacts (US-024). Mirrors backend/app/contacts/validation.py; the API re-checks everything. */

import { validateEmail } from "./validation";

export type RouteType = "EMAIL" | "PHONE" | "WEBSITE" | "CONTACT_FORM" | "HELPDESK";

export interface PolicyOwner {
  id: string;
  name: string;
  job_title: string | null;
  email: string | null;
  phone: string | null;
  policy_count?: number;
}

export interface HelpRoute {
  id: string;
  label: string;
  route_type: RouteType;
  destination: string;
  description: string | null;
  is_default?: boolean;
  policy_count?: number;
}

export interface Contacts {
  owners: PolicyOwner[];
  help_routes: HelpRoute[];
}

export const ROUTE_TYPES: { value: RouteType; label: string; destination: string }[] = [
  { value: "EMAIL", label: "Email", destination: "Email address" },
  { value: "PHONE", label: "Phone", destination: "Phone number" },
  { value: "WEBSITE", label: "Website", destination: "Web address" },
  { value: "CONTACT_FORM", label: "Contact form", destination: "Contact form web address" },
  { value: "HELPDESK", label: "Helpdesk", destination: "Helpdesk web address" },
];

export function routeTypeLabel(type: RouteType): string {
  return ROUTE_TYPES.find((t) => t.value === type)?.label ?? type;
}

/** A link for a help route destination: mailto:, tel: or the web address. */
export function routeHref(route: Pick<HelpRoute, "route_type" | "destination">): string {
  if (route.route_type === "EMAIL") return `mailto:${route.destination}`;
  if (route.route_type === "PHONE") return `tel:${route.destination.replace(/[^0-9+]/g, "")}`;
  return route.destination;
}

const PHONE = /^\+?[0-9 ()-]{6,25}$/;

export function validatePhone(value: string): string | undefined {
  const v = value.trim();
  if (!v) return;
  if (!PHONE.test(v) || v.replace(/\D/g, "").length < 6) return "Enter a valid phone number, like 0300 123 4567";
}

export function validateDestination(type: RouteType, value: string): string | undefined {
  const v = value.trim();
  if (type === "EMAIL") return v ? validateEmail(v) : "Enter the email address";
  if (type === "PHONE") return v ? validatePhone(v) : "Enter the phone number";
  if (!v) return "Enter the web address";
  try {
    const url = new URL(v.includes("://") ? v : `https://${v}`);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".")) throw new Error();
  } catch {
    return "Enter a valid website address, like https://www.organisation.org";
  }
}
