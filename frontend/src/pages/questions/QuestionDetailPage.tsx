import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, AppShell, Button, ErrorState, PageHeader, Skeleton } from "../../components";
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
  const [tracking, setTracking] = useState(false);
  const [gapError, setGapError] = useState<string>();
  const navigate = useNavigate();

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

  async function trackGap() {
    setTracking(true);
    setGapError(undefined);
    try {
      const gap = await api<{ id: string }>(`/organisations/${membership.organisation_id}/knowledge-gaps`, {
        method: "POST",
        body: JSON.stringify({ question_id: questionId }),
      });
      navigate(`/internal/knowledge-gaps/${gap.id}`);
    } catch (err) {
      const apiErr = err as ApiError;
      setGapError(apiErr.status === 409 ? apiErr.message : "We couldn't create the knowledge gap. Please try again.");
    } finally {
      setTracking(false);
    }
  }

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
        <>
          <QuestionResult answer={answer} />
          {membership.role === "ADMIN" && (
            <section className="pc-card pc-gap-action" aria-label="Knowledge gap">
              {answer.knowledge_gap_id ? (
                <p>
                  This question is tracked as a knowledge gap.{" "}
                  <Link to={`/internal/knowledge-gaps/${answer.knowledge_gap_id}`}>View knowledge gap</Link>
                </p>
              ) : (
                <>
                  <p className="pc-field__hint">
                    {answer.status === "ANSWERED"
                      ? "If this answer was wrong or incomplete, track it so the policies can be improved."
                      : "Track this question so the missing information can be added to your policies."}
                  </p>
                  {gapError && <Alert tone="error" title={gapError} />}
                  <Button variant="secondary" onClick={trackGap} loading={tracking}>
                    Track as knowledge gap
                  </Button>
                </>
              )}
            </section>
          )}
        </>
      )}
    </AppShell>
  );
}
