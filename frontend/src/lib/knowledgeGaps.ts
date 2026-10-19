/** Knowledge gaps (US-033A). */
import type { QuestionAudience } from "./questions";

export type GapStatus = "OPEN" | "INVESTIGATING" | "RESOLVED" | "CLOSED";

export const GAP_STATUSES: GapStatus[] = ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"];

export const GAP_STATUS_LABELS: Record<GapStatus, string> = {
  OPEN: "Open",
  INVESTIGATING: "Investigating",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export interface GapSummary {
  id: string;
  question: string;
  audience: QuestionAudience;
  asked_at: string;
  status: GapStatus;
  updated_at: string;
}

export interface KnowledgeGap extends GapSummary {
  question_id: string | null;
  searched_policies: { id: string; name: string; archived: boolean }[];
  notes: string | null;
  resolution: string | null;
  created_at: string;
  closed_at: string | null;
}

export interface GapList {
  gaps: GapSummary[];
  counts: Record<GapStatus, number>;
}
