import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { currentMembership, useAuth } from "../lib/auth";
import type { Answer, FeedbackReason } from "../lib/questions";
import { AnswerCard } from "./AnswerCard";
import { FeedbackButtons } from "./FeedbackButtons";
import { InsufficientEvidenceCard } from "./InsufficientEvidenceCard";

/** What a staff question got back: an answer with sources and feedback, or who to contact. */
export function QuestionResult({ answer }: { answer: Answer }) {
  const { user } = useAuth();
  const membership = currentMembership(user)!;

  async function sendFeedback(helpful: boolean, reason: FeedbackReason | null) {
    await api(`/organisations/${membership.organisation_id}/questions/${answer.id}/feedback`, {
      method: "PUT",
      body: JSON.stringify({ helpful, reason }),
    });
  }

  if (answer.status === "ANSWERED") {
    return (
      <AnswerCard
        answer={answer}
        policyHref={(c) => `/internal/policies/${c.policy_id}`}
        footer={<FeedbackButtons key={answer.id} initial={answer.feedback} onSubmit={sendFeedback} />}
      />
    );
  }
  return (
    <InsufficientEvidenceCard
      answer={answer}
      audience="internal"
      noContactHint={
        membership.role === "ADMIN" && (
          <p className="pc-field__hint">
            <Link to="/internal/contacts">Add a policy owner</Link> and assign it to policies so staff know who to ask.
          </p>
        )
      }
    />
  );
}
