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

  // Administrators can open anyone's question; only the person who asked gives feedback.
  const canGiveFeedback = answer.asked_by_me !== false;
  const isPublic = answer.audience === "PUBLIC";
  const questionLabel = canGiveFeedback ? "Your question" : "Question";

  if (answer.status === "ANSWERED") {
    return (
      <AnswerCard
        answer={answer}
        policyHref={(c) => `/internal/policies/${c.policy_id}`}
        basis={isPublic ? "Based only on your organisation's approved public policies." : undefined}
        questionLabel={questionLabel}
        footer={
          canGiveFeedback ? (
            <FeedbackButtons key={answer.id} initial={answer.feedback} onSubmit={sendFeedback} />
          ) : (
            answer.feedback && (
              <p className="pc-field__hint">
                The person who asked marked this answer {answer.feedback.helpful ? "helpful" : "unhelpful"}.
              </p>
            )
          )
        }
      />
    );
  }
  return (
    <InsufficientEvidenceCard
      answer={answer}
      audience={isPublic ? "public" : "internal"}
      questionLabel={questionLabel}
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
