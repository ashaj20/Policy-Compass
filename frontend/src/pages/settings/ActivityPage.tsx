import { useCallback, useEffect, useState } from "react";
import { AppShell, Button, EmptyState, ErrorState, PageHeader, Skeleton } from "../../components";
import { AuditTimeline } from "../../components/AuditTimeline";
import { api, ApiError } from "../../lib/api";
import type { AuditEvent } from "../../lib/audit";
import { currentMembership, useAuth } from "../../lib/auth";

interface AuditPage {
  events: AuditEvent[];
  next_before: string | null;
}

/** Read-only history of administrative changes (US-005A). Administrators only. */
export function ActivityPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const base = `/organisations/${membership.organisation_id}/audit-events`;

  const [events, setEvents] = useState<AuditEvent[]>();
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [error, setError] = useState<ApiError>();
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      const page = await api<AuditPage>(base);
      setEvents(page.events);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err as ApiError);
    }
  }, [base]);

  useEffect(() => {
    if (isAdmin) load();
  }, [load, isAdmin]);

  async function loadMore() {
    if (!nextBefore) return;
    setLoadingMore(true);
    setMoreError(undefined);
    try {
      const page = await api<AuditPage>(`${base}?before=${encodeURIComponent(nextBefore)}`);
      setEvents((prev) => [...(prev ?? []), ...page.events]);
      setNextBefore(page.next_before);
    } catch (err) {
      setMoreError((err as ApiError).message);
    } finally {
      setLoadingMore(false);
    }
  }

  if (!isAdmin) {
    return (
      <AppShell>
        <PageHeader title="Activity" />
        <ErrorState message="You don't have permission to view activity." />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Activity"
        description="A permanent record of changes made by administrators. Entries can't be edited or deleted."
      />
      <section className="pc-card">
        {error ? (
          <ErrorState message="We couldn't load activity. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !events ? (
          <Skeleton lines={6} />
        ) : events.length === 0 ? (
          <EmptyState title="No activity yet" description="Changes to your organisation will be recorded here." />
        ) : (
          <>
            <AuditTimeline events={events} />
            {moreError && (
              <p className="pc-field__error" role="alert">
                {moreError}
              </p>
            )}
            {nextBefore && (
              <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                Show older activity
              </Button>
            )}
          </>
        )}
      </section>
    </AppShell>
  );
}
