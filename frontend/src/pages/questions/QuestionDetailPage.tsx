import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell, ErrorState, PageHeader, Skeleton } from "../../components";
import { QuestionResult } from "../../components/QuestionResult";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatRelativeDay } from "../../lib/format";
import { AUDIENCE_LABELS, type Answer } from "../../lib/questions";

/** One of the member's past questions (US-019), exactly as it was answered at the time. */
export function QuestionDetailPage() {
  const { questionId } = useParams();
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const [answer, setAnswer] = useState<Answer>();
  const [error, setError] = useState<ApiError>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setAnswer(await api<Answer>(`/organisations/${membership.organisation_id}/questions/${questionId}`));
    } catch (err) {
      setError(err as ApiError);
    }
  }, [membership.organisation_id, questionId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell>
      <p>
        <Link to="/internal/questions">← Questions</Link>
      </p>
      <PageHeader
        title="Question"
        description={
          answer
            ? `${answer.asked_by_me === false && answer.audience ? `${AUDIENCE_LABELS[answer.audience]}, ` : "Asked "}${formatRelativeDay(answer.asked_at)}. Sources show the policy versions used at the time.`
            : undefined
        }
      />
      {error ? (
        error.status === 404 ? (
          <ErrorState message="This question is no longer available." />
        ) : (
          <ErrorState message="We couldn't load this question. Please try again." errorId={error.errorId} onRetry={load} />
        )
      ) : !answer ? (
        <div className="pc-card">
          <Skeleton lines={4} />
        </div>
      ) : (
        <QuestionResult answer={answer} />
      )}
    </AppShell>
  );
}
