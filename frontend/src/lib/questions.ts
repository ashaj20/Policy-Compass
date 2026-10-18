/** Questions and answers (US-016). */

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

export type AnswerStatus = "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "ERROR";

export interface Answer {
  id: string;
  question: string;
  status: AnswerStatus;
  reason: string | null;
  answer: string | null;
  citations: Citation[];
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
