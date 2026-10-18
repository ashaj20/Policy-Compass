import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell, Button, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatRelativeDay } from "../../lib/format";
import { ANSWER_STATUS_LABELS, type QuestionPage, type QuestionSummary } from "../../lib/questions";

const STATUS_FILTER = [
  { value: "", label: "All questions" },
  { value: "ANSWERED", label: "Answered" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Not enough information" },
];

const HELPFUL_TEXT = { true: "You found this helpful", false: "You found this unhelpful" } as const;

/** The member's own questions (US-019). Nobody else's questions are ever shown here. */
export function QuestionsPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [questions, setQuestions] = useState<QuestionSummary[]>();
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError>();

  const status = params.get("status") ?? "";
  const q = params.get("q") ?? "";
  const filtered = Boolean(status || q);

  const url = useCallback(
    (before?: string) => {
      const query = new URLSearchParams();
      if (status) query.set("status", status);
      if (q) query.set("q", q);
      if (before) query.set("before", before);
      const s = query.toString();
      return `/organisations/${membership.organisation_id}/questions${s ? `?${s}` : ""}`;
    },
    [membership.organisation_id, status, q],
  );

  const load = useCallback(async () => {
    setError(undefined);
    setQuestions(undefined);
    try {
      const page = await api<QuestionPage>(url());
      setQuestions(page.questions);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err as ApiError);
    }
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  // Apply the search shortly after typing stops.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (q !== search.trim()) setFilter("q", search.trim());
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  async function loadMore() {
    if (!nextBefore) return;
    setLoadingMore(true);
    try {
      const page = await api<QuestionPage>(url(nextBefore));
      setQuestions((qs) => [...(qs ?? []), ...page.questions]);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="My questions"
        description="Questions you've asked and what Policy Compass found. Only you can see these."
        actions={
          <Link to="/internal/ask" className="pc-button pc-button--primary">
            Ask a question
          </Link>
        }
      />
      <section className="pc-card" aria-label="Question history">
        <div className="pc-filters" role="search">
          <Input
            label="Search questions"
            type="search"
            placeholder="Search your questions"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pc-filters__search"
          />
          <Select label="Status" options={STATUS_FILTER} value={status} onChange={(e) => setFilter("status", e.target.value)} />
        </div>

        {error ? (
          <ErrorState message="We couldn't load your questions. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !questions ? (
          <Skeleton lines={5} />
        ) : questions.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No questions match these filters"
              description="Try a different search or clear the filters."
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSearch("");
                    setParams(new URLSearchParams(), { replace: true });
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="You haven't asked any questions yet"
              description="Ask about your organisation's approved policies and your questions will appear here."
              action={
                <Link to="/internal/ask" className="pc-button pc-button--primary">
                  Ask a question
                </Link>
              }
            />
          )
        ) : (
          <>
            <ul className="pc-history">
              {questions.map((item) => (
                <li key={item.id} className="pc-history__item">
                  <Link to={`/internal/questions/${item.id}`} className="pc-history__question">
                    {item.question}
                  </Link>
                  <div className="pc-history__meta">
                    <span className={`pc-tag pc-tag--${item.status === "ANSWERED" ? "ok" : "warning"}`}>
                      {item.status === "ANSWERED" ? "✓ " : "! "}
                      {ANSWER_STATUS_LABELS[item.status]}
                    </span>
                    <span>{formatRelativeDay(item.asked_at)}</span>
                    {item.sources.length > 0 && <span>Sources: {item.sources.join(", ")}</span>}
                    {item.helpful !== null && <span>{HELPFUL_TEXT[`${item.helpful}`]}</span>}
                  </div>
                </li>
              ))}
            </ul>
            {nextBefore && (
              <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                Show older questions
              </Button>
            )}
          </>
        )}
      </section>
    </AppShell>
  );
}
