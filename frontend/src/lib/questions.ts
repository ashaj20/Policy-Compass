/** Questions and answers (US-016, US-017). */
import type { RouteType } from "./contacts";

export interface Citation {
  policy_id: string;
  policy_name: string;
  version_id: string;
  version_label: string;
  effective_date: string;
  section: string | null;
  page: number | null;
  excerpt: string;
}

/** Who to contact when we couldn't answer (US-017). Owners are internal-only. */
export type Escalation =
  | { kind: "owner"; name: string; job_title: string | null; email: string | null; phone: string | null; policy_name: string }
  | { kind: "help_route"; label: string; route_type: RouteType; destination: string; description: string | null };

export type AnswerStatus = "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "ERROR";

export interface Answer {
  id: string;
  question: string;
  status: AnswerStatus;
  reason: string | null;
  answer: string | null;
  citations: Citation[];
  escalation: Escalation | null;
  asked_at: string;
}

/** Truthful, generic progress messages (Spec §30): these steps really happen, in this order. */
export const ASKING_STEPS = ["Searching approved policies…", "Reviewing relevant information…", "Preparing your answer…"];

export function validateQuestion(value: string): string | undefined {
  const v = value.trim();
  if (!v) return "Enter a question to get started";
  if (v.length < 3) return "Please ask a fuller question";
  if (v.length > 1000) return "Please keep your question under 1000 characters";
}
