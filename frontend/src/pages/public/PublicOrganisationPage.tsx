import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useParams } from "react-router-dom";
import { Alert, Button, ErrorState, LoadingState } from "../../components";
import { AnswerCard } from "../../components/AnswerCard";
import { FeedbackButtons } from "../../components/FeedbackButtons";
import { InsufficientEvidenceCard } from "../../components/InsufficientEvidenceCard";
import { QuestionInput } from "../../components/QuestionInput";
import { api, ApiError } from "../../lib/api";
import { brandStyle, DEFAULT_BRAND } from "../../lib/colour";
import { routeHref, type RouteType } from "../../lib/contacts";
import { ASKING_STEPS, type FeedbackReason, type PublicAnswer } from "../../lib/questions";

interface PublicHelpRoute {
  label: string;
  route_type: RouteType;
  destination: string;
  description: string | null;
}

interface PublicOrganisation {
  name: string;
  slug: string;
  website: string | null;
  logo_url: string | null;
  primary_colour: string;
  brand_text_colour: string;
  accepting_questions: boolean;
  topics: string[];
  help_route: PublicHelpRoute | null;
}

const HISTORY_LIMIT = 10;

// Session-scoped history (US-019, public): kept only in this browser tab, never on the server.
function historyKey(slug: string) {
  return `pc-public-history:${slug}`;
}

function loadHistory(slug: string): PublicAnswer[] {
  try {
    const raw = sessionStorage.getItem(historyKey(slug));
    return raw ? (JSON.parse(raw) as PublicAnswer[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(slug: string, items: PublicAnswer[]) {
  try {
    sessionStorage.setItem(historyKey(slug), JSON.stringify(items.slice(0, HISTORY_LIMIT)));
  } catch {
    // History is a convenience; asking still works without it.
  }
}

/**
 * The public page at /p/<slug> (US-026, US-027, US-029). No sign-in. Answers come only from the
 * organisation's approved public policies, and only public help routes are ever shown. No internal
 * navigation, contacts or data appear here.
 */
export function PublicOrganisationPage() {
  const { slug = "" } = useParams();
  const [org, setOrg] = useState<PublicOrganisation>();
  const [loadError, setLoadError] = useState<ApiError>();
  const [answer, setAnswer] = useState<PublicAnswer>();
  const [asking, setAsking] = useState(false);
  const [step, setStep] = useState(0);
  const [askError, setAskError] = useState<ApiError>();
  const [history, setHistory] = useState<PublicAnswer[]>(() => loadHistory(slug));
  const [inputKey, setInputKey] = useState(0);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOrg(undefined);
    setLoadError(undefined);
    setHistory(loadHistory(slug));
    api<PublicOrganisation>(`/public/organisations/${encodeURIComponent(slug)}`)
      .then(setOrg)
      .catch(setLoadError);
  }, [slug]);

  useEffect(() => {
    if (!asking) return;
    const timers = [setTimeout(() => setStep(1), 1200), setTimeout(() => setStep(2), 2600)];
    return () => timers.forEach(clearTimeout);
  }, [asking]);

  function remember(item: PublicAnswer) {
    setHistory((items) => {
      const next = [item, ...items.filter((i) => i.id !== item.id)].slice(0, HISTORY_LIMIT);
      saveHistory(slug, next);
      return next;
    });
  }

  async function ask(question: string) {
    setAsking(true);
    setStep(0);
    setAskError(undefined);
    setAnswer(undefined);
    try {
      const result = await api<PublicAnswer>(`/public/organisations/${encodeURIComponent(slug)}/questions`, {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setAnswer(result);
      remember(result);
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (err) {
      setAskError(err as ApiError);
    } finally {
      setAsking(false);
    }
  }

  async function sendFeedback(helpful: boolean, reason: FeedbackReason | null) {
    if (!answer) return;
    await api(`/public/organisations/${encodeURIComponent(slug)}/questions/${answer.id}/feedback`, {
      method: "PUT",
      body: JSON.stringify({ helpful, reason }),
    });
    remember({ ...answer, feedback: { helpful, reason } });
  }

  function askAnother() {
    setAnswer(undefined);
    setAskError(undefined);
    setInputKey((k) => k + 1);
  }

  if (loadError) {
    return (
      <main className="pc-public">
        <ErrorState message={loadError.status === 404 ? loadError.message : "We couldn't load this page. Please try again."} />
      </main>
    );
  }
  if (!org) return <LoadingState label="Loading…" />;

  return (
    <div className="pc-public" style={brandStyle(org.primary_colour ?? DEFAULT_BRAND, org.brand_text_colour) as CSSProperties}>
      <header className="pc-public__header">
        {org.logo_url && <img src={org.logo_url} alt="" className="pc-public__logo" />}
        <span className="pc-public__name">{org.name}</span>
      </header>

      <main className="pc-public__main">
        <div className="pc-public__hero">
          <h1>How can we help?</h1>
          <p className="pc-auth__muted">Ask a question about {org.name}'s policies and services.</p>
        </div>

        {!org.accepting_questions ? (
          <section className="pc-card">
            <p>{org.name}'s policy questions page is being set up. Please check back soon.</p>
          </section>
        ) : (
          <>
            <section className="pc-card pc-public__ask">
              <QuestionInput
                key={inputKey}
                label="What would you like to know?"
                placeholder="e.g. How do I report a repair?"
                busy={asking}
                onAsk={ask}
              />
              {org.topics.length > 0 && !answer && (
                <p className="pc-field__hint">You can ask about: {org.topics.join(", ")}.</p>
              )}
            </section>

            <div ref={resultRef} tabIndex={-1} className="pc-ask__result" aria-live="polite">
              {asking && (
                <div className="pc-asking" role="status">
                  <span className="pc-spinner pc-spinner--lg" aria-hidden="true" />
                  <p>{ASKING_STEPS[step]}</p>
                </div>
              )}
              {askError && (
                <Alert
                  tone="error"
                  title={
                    askError.status === 429 || askError.status === 0
                      ? askError.message
                      : "We couldn't get an answer. Please try again."
                  }
                />
              )}
              {answer?.status === "ANSWERED" && (
                <AnswerCard
                  answer={answer}
                  basis={`Based only on ${org.name}'s approved public policies.`}
                  footer={<FeedbackButtons key={answer.id} initial={answer.feedback} onSubmit={sendFeedback} />}
                />
              )}
              {answer && answer.status !== "ANSWERED" && <InsufficientEvidenceCard answer={answer} audience="public" />}
              {answer && (
                <Button variant="secondary" onClick={askAnother} className="pc-auth__spaced">
                  Ask another question
                </Button>
              )}
            </div>

            {history.length > 0 && (
              <section className="pc-card pc-public__history" aria-labelledby="public-history-heading">
                <h2 id="public-history-heading" className="pc-card__title">
                  Your questions
                </h2>
                <p className="pc-field__hint">Only shown in this browser tab, and cleared when you close it.</p>
                <ul className="pc-history">
                  {history.map((item) => (
                    <li key={item.id} className="pc-history__item">
                      <button
                        type="button"
                        className="pc-link-button pc-history__question"
                        onClick={() => {
                          setAskError(undefined);
                          setAnswer(item);
                          requestAnimationFrame(() => resultRef.current?.focus());
                        }}
                      >
                        {item.question}
                      </button>
                      <div className="pc-history__meta">
                        {item.status === "ANSWERED" ? "Answered" : "We couldn't find enough information"}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>

      <footer className="pc-public__footer">
        {org.help_route && (
          <section aria-labelledby="need-help-heading" className="pc-public__help">
            <h2 id="need-help-heading" className="pc-answer__heading pc-answer__heading--small">
              Need more help?
            </h2>
            <p>
              <a href={routeHref(org.help_route)} rel="noopener noreferrer">
                {org.help_route.label}
              </a>
              {org.help_route.description && <> · {org.help_route.description}</>}
            </p>
          </section>
        )}
        <p className="pc-field__hint">
          Answers are based only on {org.name}'s approved public policies. Please don't include personal information in your
          questions.
        </p>
        {org.website && (
          <p>
            <a href={org.website} rel="noopener noreferrer">
              Visit {org.name}'s website
            </a>
          </p>
        )}
      </footer>
    </div>
  );
}
