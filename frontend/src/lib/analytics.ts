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
