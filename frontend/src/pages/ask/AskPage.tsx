import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, AppShell, Button, PageHeader } from "../../components";
import { QuestionResult } from "../../components/QuestionResult";
import { QuestionInput } from "../../components/QuestionInput";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { ASKING_STEPS, type Answer } from "../../lib/questions";

const EXAMPLES = [
  "How do I report a repair?",
  "What is our complaints process?",
  "How quickly should emergencies be dealt with?",
];

/** Ask a policy question (US-016). Answers come only from approved, active policies. */
export function AskPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const [params, setParams] = useSearchParams();
  const [answer, setAnswer] = useState<Answer>();
  const [asking, setAsking] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<ApiError>();
  const [inputKey, setInputKey] = useState(0);
  const resultRef = useRef<HTMLDivElement>(null);
  const autoAsked = useRef(false);

  const ask = useCallback(
    async (question: string) => {
      setAsking(true);
      setError(undefined);
      setAnswer(undefined);
      setStep(0);
      try {
        const result = await api<Answer>(`/organisations/${membership.organisation_id}/questions`, {
          method: "POST",
          body: JSON.stringify({ question }),
        });
        setAnswer(result);
        requestAnimationFrame(() => resultRef.current?.focus());
      } catch (err) {
        setError(err as ApiError);
      } finally {
        setAsking(false);
      }
    },
    [membership.organisation_id],
  );

  // Advance the progress message while waiting; these stages really happen in this order.
  useEffect(() => {
    if (!asking) return;
    const timers = [setTimeout(() => setStep(1), 1200), setTimeout(() => setStep(2), 2600)];
    return () => timers.forEach(clearTimeout);
  }, [asking]);

  // A question passed from the dashboard (?q=...) is asked straight away, once.
  useEffect(() => {
    const q = params.get("q");
    if (q && !autoAsked.current) {
      autoAsked.current = true;
      setParams({}, { replace: true });
      ask(q);
    }
  }, [params, setParams, ask]);

  function askAnother() {
    setAnswer(undefined);
    setError(undefined);
    setInputKey((k) => k + 1);
  }

  return (
    <AppShell>
      <PageHeader title="Ask a policy question" description="Search your organisation's approved policies and guidance." />
      <section className="pc-card">
        <QuestionInput
          key={inputKey}
          label="What would you like to know?"
          placeholder="e.g. How quickly should emergency repairs be handled?"
          examples={answer || asking ? [] : EXAMPLES}
          busy={asking}
          onAsk={ask}
        />
      </section>

      <div ref={resultRef} tabIndex={-1} className="pc-ask__result" aria-live="polite">
        {asking && (
          <div className="pc-asking" role="status">
            <span className="pc-spinner pc-spinner--lg" aria-hidden="true" />
            <p>{ASKING_STEPS[step]}</p>
          </div>
        )}
        {error && (
          <Alert tone="error" title={error.status === 0 ? error.message : "We couldn't get an answer. Please try again."}>
            {error.errorId && <p>Reference: {error.errorId}</p>}
          </Alert>
        )}
        {answer && <QuestionResult answer={answer} />}
        {answer && (
          <Button variant="secondary" onClick={askAnother} className="pc-auth__spaced">
            Ask another question
          </Button>
        )}
      </div>
    </AppShell>
  );
}
