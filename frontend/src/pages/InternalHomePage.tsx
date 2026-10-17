import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Alert, AppShell, ErrorState, PageHeader, Skeleton } from "../components";
import { AuditTimeline } from "../components/AuditTimeline";
import { api, ApiError } from "../lib/api";
import type { AuditEvent } from "../lib/audit";
import { currentMembership, useAuth } from "../lib/auth";
import { formatRelativeDay } from "../lib/format";

interface Dashboard {
  counts: {
    total: number;
    active: number;
    awaiting_approval: number;
    drafts_to_review: number;
    processing: number;
    failed: number;
    archived: number;
  };
  attention: { kind: "failed" | "awaiting_approval" | "draft"; policy_id: string; policy_name: string; version: string; since: string }[];
  setup: { key: string; done: boolean }[];
}

const ROLE_LABELS = { ADMIN: "Administrator", STAFF: "Staff member" } as const;

const SETUP_STEPS: Record<string, { label: string; to?: string }> = {
  organisation: { label: "Organisation created" },
  policy: { label: "Upload your first policy", to: "/internal/policies/new" },
  owner: { label: "Add a policy owner for staff escalation", to: "/internal/contacts" },
  help_route: { label: "Add a public help route", to: "/internal/contacts" },
  branding: { label: "Add your logo or brand colour", to: "/internal/settings/branding" },
};

const ATTENTION_TEXT = {
  failed: { icon: "✕", text: "couldn't be processed" },
  awaiting_approval: { icon: "◷", text: "is ready for approval" },
  draft: { icon: "○", text: "needs reviewing and marking ready" },
};

function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** The internal dashboard (US-021). Question metrics join once questions exist. */
export function InternalHomePage() {
  const { user } = useAuth();
  const state = useLocation().state as { created?: boolean; notice?: string } | null;
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const base = `/organisations/${membership.organisation_id}`;

  const [data, setData] = useState<Dashboard>();
  const [activity, setActivity] = useState<AuditEvent[]>();
  const [error, setError] = useState<ApiError>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setData(await api<Dashboard>(`${base}/dashboard`));
      if (isAdmin) {
        const page = await api<{ events: AuditEvent[] }>(`${base}/audit-events?limit=5`);
        setActivity(page.events);
      }
    } catch (err) {
      setError(err as ApiError);
    }
  }, [base, isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  const setupLeft = data?.setup.filter((s) => !s.done).length ?? 0;

  const cards = data
    ? [
        { label: "Active policies", value: data.counts.active, to: "/internal/policies?status=ACTIVE", tone: "ok" },
        { label: "Awaiting approval", value: data.counts.awaiting_approval, to: "#needs-attention", tone: "warn", adminOnly: true },
        { label: "Drafts to review", value: data.counts.drafts_to_review, to: "#needs-attention", tone: "muted" },
        { label: "Processing", value: data.counts.processing, to: "/internal/policies?status=PROCESSING", tone: "info", adminOnly: true },
        { label: "Failed", value: data.counts.failed, to: "/internal/policies?status=FAILED", tone: "bad", adminOnly: true },
      ].filter((c) => isAdmin || !c.adminOnly)
    : [];

  return (
    <AppShell>
      <PageHeader title={membership.organisation_name} description={`${greeting()}. Here's what's happening with your policies.`} />
      {state?.created && <Alert tone="success" title="Your organisation has been created." />}
      {state?.notice && <Alert tone="warning" title={state.notice} />}
      <p className="pc-field__hint">
        Signed in as {user?.email} · {ROLE_LABELS[membership.role]}
      </p>

      {error ? (
        <ErrorState message="We couldn't load your dashboard. Please try again." errorId={error.errorId} onRetry={load} />
      ) : !data ? (
        <div className="pc-card">
          <Skeleton lines={5} />
        </div>
      ) : (
        <>
          {isAdmin && setupLeft > 0 && (
            <section className="pc-card" aria-labelledby="setup-heading">
              <h2 id="setup-heading" className="pc-card__title">
                Let's get your knowledge base ready
              </h2>
              <ul className="pc-checklist">
                {data.setup.map((s) => {
                  const step = SETUP_STEPS[s.key];
                  return (
                    <li key={s.key} className={s.done ? "pc-checklist__item--done" : ""}>
                      <span aria-hidden="true">{s.done ? "✓" : "○"}</span>{" "}
                      {s.done || !step.to ? step.label : <Link to={step.to}>{step.label}</Link>}
                      <span className="visually-hidden">{s.done ? " (done)" : " (to do)"}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          <section aria-label="Policy summary" className="pc-stat-grid">
            {cards.map((c) => (
              <Link key={c.label} to={c.to} className={`pc-stat pc-stat--${c.tone}`}>
                <span className="pc-stat__value">{c.value}</span>
                <span className="pc-stat__label">{c.label}</span>
              </Link>
            ))}
          </section>

          <section className="pc-card" aria-labelledby="needs-attention-heading" id="needs-attention" tabIndex={-1}>
            <h2 id="needs-attention-heading" className="pc-card__title">
              Needs attention
            </h2>
            {data.attention.length === 0 ? (
              <p className="pc-auth__muted">Nothing needs your attention right now.</p>
            ) : (
              <ul className="pc-attention">
                {data.attention.map((a) => (
                  <li key={`${a.policy_id}-${a.kind}`} className={`pc-attention__item pc-attention__item--${a.kind}`}>
                    <span aria-hidden="true">{ATTENTION_TEXT[a.kind].icon}</span>
                    <span>
                      <Link to={`/internal/policies/${a.policy_id}`}>{a.policy_name}</Link> version {a.version}{" "}
                      {ATTENTION_TEXT[a.kind].text}
                    </span>
                    <span className="pc-field__hint">{formatRelativeDay(a.since)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {isAdmin && activity && activity.length > 0 && (
            <section className="pc-card" aria-labelledby="recent-activity-heading">
              <h2 id="recent-activity-heading" className="pc-card__title">
                Recent activity
              </h2>
              <AuditTimeline events={activity} />
              <Link to="/internal/settings/activity">See all activity</Link>
            </section>
          )}

          {data.counts.total === 0 && !isAdmin && (
            <p className="pc-auth__muted">Your administrators haven't published any policies yet.</p>
          )}
          <p className="pc-field__hint">
            Public page: <Link to={`/p/${membership.organisation_slug}`}>/p/{membership.organisation_slug}</Link>
          </p>
        </>
      )}
    </AppShell>
  );
}
