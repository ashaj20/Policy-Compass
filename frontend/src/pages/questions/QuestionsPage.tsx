import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell, Button, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatRelativeDay } from "../../lib/format";
import { ANSWER_STATUS_LABELS, AUDIENCE_LABELS, type QuestionPage, type QuestionSummary } from "../../lib/questions";

const STATUS_FILTER = [
  { value: "", label: "All questions" },
  { value: "ANSWERED", label: "Answered" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Unanswered" },
];

const SCOPE_OPTIONS = [
  { value: "all", label: "Everyone's questions" },
  { value: "mine", label: "My questions" },
];

const AUDIENCE_FILTER = [
  { value: "", label: "Staff and public" },
  { value: "INTERNAL", label: "Staff" },
  { value: "PUBLIC", label: "Public" },
];

const FILTER_KEYS = ["status", "q", "audience", "from", "to"];

/**
 * Question history. Members see their own questions (US-019). Administrators can also see every
 * question in the organisation, staff and public (US-032), and the unanswered ones that point to
 * knowledge gaps (US-033). Who asked is never shown.
 */
export function QuestionsPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [questions, setQuestions] = useState<QuestionSummary[]>();
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError>();

  const scope = isAdmin && params.get("scope") !== "mine" ? "all" : "mine";
  const everyone = scope === "all";
  const query = new URLSearchParams();
  if (everyone) query.set("scope", "all");
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value && (everyone || ["status", "q"].includes(key))) query.set(key, value);
  }
  const queryString = query.toString();
  const filtered = FILTER_KEYS.some((k) => query.has(k));

  const url = useCallback(
    (before?: string) => {
      const q = new URLSearchParams(queryString);
      if (before) q.set("before", before);
      return `/organisations/${membership.organisation_id}/questions?${q.toString()}`;
    },
    [membership.organisation_id, queryString],
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
      if ((params.get("q") ?? "") !== search.trim()) setFilter("q", search.trim());
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

  function clearFilters() {
    setSearch("");
    const next = new URLSearchParams();
    if (params.get("scope")) next.set("scope", params.get("scope")!);
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
        title={everyone ? "Questions" : "My questions"}
        description={
          everyone
            ? "What staff and the public have been asking. Unanswered questions show where policies may need adding or updating."
            : "Questions you've asked and what Policy Compass found. Administrators can see questions asked in your organisation, but not who asked them."
        }
        actions={
          <Link to="/internal/ask" className="pc-button pc-button--primary">
            Ask a question
          </Link>
        }
      />
      <section className="pc-card" aria-label="Question history">
        <div className="pc-filters" role="search">
          {isAdmin && (
            <Select label="Show" options={SCOPE_OPTIONS} value={scope} onChange={(e) => setFilter("scope", e.target.value)} />
          )}
          <Input
            label="Search questions"
            type="search"
            placeholder={everyone ? "Search questions" : "Search your questions"}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pc-filters__search"
          />
          <Select label="Status" options={STATUS_FILTER} value={params.get("status") ?? ""} onChange={(e) => setFilter("status", e.target.value)} />
          {everyone && (
            <>
              <Select
                label="Audience"
                options={AUDIENCE_FILTER}
                value={params.get("audience") ?? ""}
                onChange={(e) => setFilter("audience", e.target.value)}
              />
              <Input label="From" type="date" value={params.get("from") ?? ""} onChange={(e) => setFilter("from", e.target.value)} />
              <Input label="To" type="date" value={params.get("to") ?? ""} onChange={(e) => setFilter("to", e.target.value)} />
            </>
          )}
        </div>

        {error ? (
          <ErrorState message="We couldn't load these questions. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !questions ? (
          <Skeleton lines={5} />
        ) : questions.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No questions match these filters"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : everyone ? (
            <EmptyState
              title="No questions yet"
              description="Questions from staff and from your public page will appear here."
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
                    {everyone && <span>{AUDIENCE_LABELS[item.audience]}</span>}
                    <span>{formatRelativeDay(item.asked_at)}</span>
                    {item.sources.length > 0 && <span>Sources: {item.sources.join(", ")}</span>}
                    {item.helpful !== null && <span>{item.helpful ? "Marked helpful" : "Marked unhelpful"}</span>}
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
