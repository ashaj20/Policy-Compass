/** Questions and answers (US-016 to US-020). */
import type { RouteType } from "./contacts";

/** What anyone, including the public, may see about a source. */
export interface PublicCitation {
  policy_name: string;
  version_label: string;
  effective_date: string;
  section: string | null;
  page: number | null;
  excerpt: string;
}

/** A source as staff see it, with the IDs needed to open the policy. */
export interface Citation extends PublicCitation {
  policy_id: string;
  version_id: string;
}

/** Who to contact when we couldn't answer (US-017). Owners are internal-only. */
export type Escalation =
  | { kind: "owner"; name: string; job_title: string | null; email: string | null; phone: string | null; policy_name: string }
  | { kind: "help_route"; label: string; route_type: RouteType; destination: string; description: string | null };

export type FeedbackReason = "INCORRECT" | "UNCLEAR" | "NOT_FOUND" | "OTHER";

export interface Feedback {
  helpful: boolean;
  reason: FeedbackReason | null;
}

/** Optional reasons for a "No" (Spec §17). */
export const FEEDBACK_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "INCORRECT", label: "The answer was incorrect" },
  { value: "UNCLEAR", label: "The answer was unclear" },
  { value: "NOT_FOUND", label: "I couldn't find what I needed" },
  { value: "OTHER", label: "Other" },
];

export type AnswerStatus = "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "ERROR";

export interface Answer {
  id: string;
  question: string;
  status: AnswerStatus;
  reason: string | null;
  answer: string | null;
  citations: Citation[];
  escalation: Escalation | null;
  feedback?: Feedback | null;
  asked_at: string;
}

export interface QuestionSummary {
  id: string;
  question: string;
  status: AnswerStatus;
  reason: string | null;
  sources: string[];
  helpful: boolean | null;
  asked_at: string;
}

export interface QuestionPage {
  questions: QuestionSummary[];
  next_before: string | null;
}

export const ANSWER_STATUS_LABELS: Record<AnswerStatus, string> = {
  ANSWERED: "Answered",
  INSUFFICIENT_EVIDENCE: "Not enough information",
  ERROR: "Error",
};

/** Truthful, generic progress messages (Spec §30): these steps really happen, in this order. */
export const ASKING_STEPS = ["Searching approved policies…", "Reviewing relevant information…", "Preparing your answer…"];

export function validateQuestion(value: string): string | undefined {
  const v = value.trim();
  if (!v) return "Enter a question to get started";
  if (v.length < 3) return "Please ask a fuller question";
  if (v.length > 1000) return "Please keep your question under 1000 characters";
}

/** A public answer (US-027): public-safe citations and only ever a public help route. */
export interface PublicAnswer {
  id: string;
  question: string;
  status: AnswerStatus;
  reason: string | null;
  answer: string | null;
  citations: PublicCitation[];
  escalation: Extract<Escalation, { kind: "help_route" }> | null;
  feedback: Feedback | null;
}
