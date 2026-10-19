import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Alert, AppShell, ErrorState, PageHeader, Skeleton } from "../components";
import { AuditTimeline } from "../components/AuditTimeline";
import { QuestionInput } from "../components/QuestionInput";
import { api, ApiError } from "../lib/api";
import type { AuditEvent } from "../lib/audit";
import { currentMembership, useAuth } from "../lib/auth";
import { formatRelativeDay } from "../lib/format";
import { usageText, type OperationalStatus, type PolicyUsageList } from "../lib/analytics";
import { ANSWER_STATUS_LABELS, type QuestionPage, type QuestionSummary } from "../lib/questions";

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
  /** Last 7 days; administrators only. */
  questions: { total: number; internal: number; public: number; answered: number; unanswered: number; open_gaps: number } | null;
}

/** The first day of the dashboard's "this week" (the last 7 days), as YYYY-MM-DD. */
function weekStart(now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
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
  const navigate = useNavigate();
  const state = useLocation().state as { created?: boolean; notice?: string } | null;
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const base = `/organisations/${membership.organisation_id}`;

  const [data, setData] = useState<Dashboard>();
  const [activity, setActivity] = useState<AuditEvent[]>();
  const [recent, setRecent] = useState<QuestionSummary[]>();
  const [usage, setUsage] = useState<PolicyUsageList>();
  const [ops, setOps] = useState<OperationalStatus>();
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

  // Most and least used policies (US-034) and operational alerts (US-035A). Admins only; optional.
  useEffect(() => {
    if (!isAdmin) return;
    api<PolicyUsageList>(`${base}/policy-usage`)
      .then(setUsage)
      .catch(() => setUsage(undefined));
    api<OperationalStatus>(`${base}/operational-status`)
      .then(setOps)
      .catch(() => setOps(undefined));
  }, [base, isAdmin]);

  // The member's own recent questions (US-025). Optional: the dashboard works without them.
  useEffect(() => {
    api<QuestionPage>(`${base}/questions?limit=3`)
      .then((page) => setRecent(page.questions))
      .catch(() => setRecent([]));
  }, [base]);

  const setupLeft = data?.setup.filter((s) => !s.done).length ?? 0;

  const cards = data
    ? [
        { label: "Active policies", value: data.counts.active, to: "/internal/policies?status=ACTIVE", tone: "ok" },
        { label: "Awaiting approval", value: data.counts.awaiting_approval, to: "#needs-attention", tone: "warn", adminOnly: true },
        { label: "Drafts to review", value: data.counts.drafts_to_review, to: "#needs-attention", tone: "muted" },
        { label: "Processing", value: data.counts.processing, to: "/internal/policies?status=PROCESSING", tone: "info", adminOnly: true },
        { label: "Failed", value: data.counts.failed, to: "/internal/policies?status=FAILED", tone: "bad", adminOnly: true },
        ...(data.questions
          ? [
              {
                label: "Questions this week",
                value: data.questions.total,
                detail: `${data.questions.internal} staff · ${data.questions.public} public`,
                to: `/internal/questions?scope=all&from=${weekStart()}`,
                tone: "info",
                adminOnly: true,
              },
              {
                label: "Unanswered this week",
                value: data.questions.unanswered,
                to: `/internal/questions?scope=all&status=INSUFFICIENT_EVIDENCE&from=${weekStart()}`,
                tone: data.questions.unanswered > 0 ? "warn" : "muted",
                adminOnly: true,
              },
              {
                label: "Open knowledge gaps",
                value: data.questions.open_gaps,
                to: "/internal/knowledge-gaps",
                tone: "muted",
                adminOnly: true,
              },
            ]
          : []),
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

      <section className="pc-card">
        <QuestionInput
          label="Ask a policy question"
          placeholder="e.g. How quickly should emergency repairs be handled?"
          onAsk={(q) => navigate(`/internal/ask?q=${encodeURIComponent(q)}`)}
        />
        {recent && recent.length > 0 && (
          <div className="pc-recent" aria-labelledby="recent-questions-heading">
            <h2 id="recent-questions-heading" className="pc-answer__heading pc-answer__heading--small">
              Your recent questions
            </h2>
            <ul className="pc-history">
              {recent.map((q) => (
                <li key={q.id} className="pc-history__item">
                  <Link to={`/internal/questions/${q.id}`} className="pc-history__question">
                    {q.question}
                  </Link>
                  <div className="pc-history__meta">
                    <span>{ANSWER_STATUS_LABELS[q.status]}</span>
                    <span>{formatRelativeDay(q.asked_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
            <Link to="/internal/questions">See all your questions</Link>
          </div>
        )}
      </section>

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
                {"detail" in c && c.detail && <span className="pc-stat__detail">{c.detail}</span>}
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

          {isAdmin && ops && <OperationalStatusCard status={ops} />}

          {isAdmin && usage && usage.policies.length > 0 && <PolicyUsageCard usage={usage} />}

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

/** Which policies are answering questions, and which active ones aren't (US-034). */
function PolicyUsageCard({ usage }: { usage: PolicyUsageList }) {
  const used = usage.policies.filter((p) => p.questions > 0).slice(0, 5);
  const unused = usage.policies.filter((p) => p.active && p.questions === 0);
  return (
    <section className="pc-card" aria-labelledby="usage-heading">
      <h2 id="usage-heading" className="pc-card__title">
        Most used policies
      </h2>
      <p className="pc-field__hint">Questions answered using each policy in the last {usage.days} days.</p>
      {used.length === 0 ? (
        <p className="pc-auth__muted">No policies have been used to answer questions yet.</p>
      ) : (
        <ul className="pc-usage">
          {used.map((p) => (
            <li key={p.policy_id} className="pc-usage__item">
              <Link to={`/internal/policies/${p.policy_id}`}>{p.name}</Link>
              <span>
                {usageText(p)}
                {p.last_used && <span className="pc-field__hint"> · last used {formatRelativeDay(p.last_used)}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {unused.length > 0 && (
        <p className="pc-field__hint">
          Not used yet: {unused.map((p) => p.name).join(", ")}.
        </p>
      )}
    </section>
  );
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Problems affecting the knowledge experience, in plain language (US-035A, Spec §23). */
function OperationalStatusCard({ status }: { status: OperationalStatus }) {
  const alerts: { key: string; text: string; to?: string }[] = [];
  if (status.processing_failures > 0)
    alerts.push({
      key: "failed",
      text: `${plural(status.processing_failures, "policy upload")} couldn't be processed`,
      to: "/internal/policies?status=FAILED",
    });
  if (status.service_unavailable > 0)
    alerts.push({
      key: "unavailable",
      text: `${plural(status.service_unavailable, "question")} couldn't be answered because the answering service was unavailable`,
    });
  if (status.limit_reached > 0)
    alerts.push({
      key: "limit",
      text: `${plural(status.limit_reached, "question")} went unanswered because the daily answer limit was reached`,
    });
  for (const p of status.negative_feedback)
    alerts.push({
      key: `feedback-${p.policy_id}`,
      text: `${plural(p.unhelpful, "answer")} using ${p.name} marked unhelpful in the last 30 days`,
      to: `/internal/questions?scope=all&feedback=unhelpful&policy_id=${p.policy_id}`,
    });
  const nearLimit = status.answers_today >= status.daily_answer_limit * 0.8;

  return (
    <section className="pc-card" aria-labelledby="ops-heading">
      <h2 id="ops-heading" className="pc-card__title">
        Operational status
      </h2>
      {alerts.length === 0 ? (
        <p className="pc-ops__ok">
          <span aria-hidden="true">✓ </span>No problems in the last {status.days} days.
        </p>
      ) : (
        <ul className="pc-ops">
          {alerts.map((a) => (
            <li key={a.key} className="pc-ops__alert">
              <span aria-hidden="true">! </span>
              {a.to ? <Link to={a.to}>{a.text}</Link> : a.text}
            </li>
          ))}
        </ul>
      )}
      <p className="pc-field__hint">
        {status.unanswered > 0 ? (
          <Link to="/internal/questions?scope=all&status=INSUFFICIENT_EVIDENCE">
            {plural(status.unanswered, "unanswered question")} in the last {status.days} days
          </Link>
        ) : (
          `No unanswered questions in the last ${status.days} days`
        )}
        {" · "}
        <span className={nearLimit ? "pc-ops__warn" : undefined}>
          {status.answers_today} of {status.daily_answer_limit} answers used today
        </span>
      </p>
    </section>
  );
}
