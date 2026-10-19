/** Policy usage (US-034). */

export interface PolicyUsage {
  policy_id: string;
  name: string;
  active: boolean;
  questions: number;
  last_used: string | null;
}

export interface PolicyUsageList {
  days: number;
  policies: PolicyUsage[];
}

export function usageText(u: Pick<PolicyUsage, "questions">): string {
  return u.questions === 1 ? "1 question" : `${u.questions} questions`;
}

/** Operational status (US-035A), last 7 days. */
export interface OperationalStatus {
  days: number;
  processing_failures: number;
  unanswered: number;
  service_unavailable: number;
  limit_reached: number;
  answers_today: number;
  daily_answer_limit: number;
  negative_feedback: { policy_id: string; name: string; unhelpful: number }[];
}
