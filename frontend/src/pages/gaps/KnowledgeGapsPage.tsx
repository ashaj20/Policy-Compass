import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell, EmptyState, ErrorState, PageHeader, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatRelativeDay } from "../../lib/format";
import { GAP_STATUS_LABELS, GAP_STATUSES, type GapList, type GapStatus } from "../../lib/knowledgeGaps";
import { AUDIENCE_LABELS } from "../../lib/questions";

/** Knowledge gaps (US-033A): unanswered questions being turned into policy improvements. */
export function KnowledgeGapsPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as GapStatus | "";
  const [data, setData] = useState<GapList>();
  const [error, setError] = useState<ApiError>();

  const load = useCallback(async () => {
    setError(undefined);
    setData(undefined);
    try {
      setData(
        await api<GapList>(`/organisations/${membership.organisation_id}/knowledge-gaps${status ? `?status=${status}` : ""}`),
      );
    } catch (err) {
      setError(err as ApiError);
    }
  }, [membership.organisation_id, status]);

  useEffect(() => {
    if (isAdmin) load();
  }, [load, isAdmin]);

  if (!isAdmin) {
    return (
      <AppShell>
        <PageHeader title="Knowledge gaps" />
        <ErrorState message="You don't have permission to view knowledge gaps." />
      </AppShell>
    );
  }

  const total = data ? GAP_STATUSES.reduce((n, s) => n + data.counts[s], 0) : 0;
  const tabs: { value: GapStatus | ""; label: string; count?: number }[] = [
    { value: "", label: "All", count: data ? total : undefined },
    ...GAP_STATUSES.map((s) => ({ value: s, label: GAP_STATUS_LABELS[s], count: data?.counts[s] })),
  ];

  return (
    <AppShell>
      <PageHeader
        title="Knowledge gaps"
        description="Questions your policies couldn't answer well, tracked until the knowledge base is improved."
        actions={
          <Link to="/internal/questions?scope=all&status=INSUFFICIENT_EVIDENCE" className="pc-button pc-button--secondary">
            Review unanswered questions
          </Link>
        }
      />
      <section className="pc-card" aria-label="Knowledge gap list">
        <nav aria-label="Filter by status" className="pc-tabs">
          {tabs.map((t) => (
            <button
              key={t.value || "all"}
              type="button"
              className="pc-tabs__tab"
              aria-pressed={status === t.value}
              onClick={() => setParams(t.value ? { status: t.value } : {}, { replace: true })}
            >
              {t.label}
              {t.count !== undefined && <> <span className="pc-tabs__count">{t.count}</span></>}
            </button>
          ))}
        </nav>

        {error ? (
          <ErrorState message="We couldn't load knowledge gaps. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !data ? (
          <Skeleton lines={5} />
        ) : data.gaps.length === 0 ? (
          total === 0 ? (
            <EmptyState
              title="No knowledge gaps yet"
              description="Open an unanswered question and choose “Track as knowledge gap” to start tracking what your policies are missing."
              action={
                <Link to="/internal/questions?scope=all&status=INSUFFICIENT_EVIDENCE" className="pc-button pc-button--primary">
                  Review unanswered questions
                </Link>
              }
            />
          ) : (
            <EmptyState title={`No ${GAP_STATUS_LABELS[status as GapStatus].toLowerCase()} gaps`} description="Choose another status to see other gaps." />
          )
        ) : (
          <ul className="pc-history">
            {data.gaps.map((g) => (
              <li key={g.id} className="pc-history__item">
                <Link to={`/internal/knowledge-gaps/${g.id}`} className="pc-history__question">
                  {g.question}
                </Link>
                <div className="pc-history__meta">
                  <span className={`pc-tag pc-tag--gap-${g.status.toLowerCase()}`}>{GAP_STATUS_LABELS[g.status]}</span>
                  <span>{AUDIENCE_LABELS[g.audience]}</span>
                  <span>Asked {formatRelativeDay(g.asked_at)}</span>
                  <span>Updated {formatRelativeDay(g.updated_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  );
}
