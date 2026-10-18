/** Questions and answers (US-016 to US-020). */
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
