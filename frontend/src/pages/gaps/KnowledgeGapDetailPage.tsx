import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, AppShell, Button, ErrorState, PageHeader, Select, Skeleton } from "../../components";
import { Textarea } from "../../components/Textarea";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatRelativeDay } from "../../lib/format";
import { GAP_STATUS_LABELS, GAP_STATUSES, type GapStatus, type KnowledgeGap } from "../../lib/knowledgeGaps";
import { AUDIENCE_LABELS } from "../../lib/questions";

const STATUS_OPTIONS = GAP_STATUSES.map((s) => ({ value: s, label: GAP_STATUS_LABELS[s] }));

/** One knowledge gap (US-033A): the original question, what was searched, and its progress. */
export function KnowledgeGapDetailPage() {
  const { gapId } = useParams();
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const url = `/organisations/${membership.organisation_id}/knowledge-gaps/${gapId}`;
  const [gap, setGap] = useState<KnowledgeGap>();
  const [loadError, setLoadError] = useState<ApiError>();
  const [status, setStatus] = useState<GapStatus>("OPEN");
  const [notes, setNotes] = useState("");
  const [resolution, setResolution] = useState("");
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string }>();

  const fill = (g: KnowledgeGap) => {
    setGap(g);
    setStatus(g.status);
    setNotes(g.notes ?? "");
    setResolution(g.resolution ?? "");
  };

  const load = useCallback(async () => {
    setLoadError(undefined);
    try {
      fill(await api<KnowledgeGap>(url));
    } catch (err) {
      setLoadError(err as ApiError);
    }
  }, [url]);

  useEffect(() => {
    if (isAdmin) load();
  }, [load, isAdmin]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setNotice(undefined);
    setFieldErrors({});
    if (status === "RESOLVED" && !resolution.trim()) {
      setFieldErrors({ resolution: "Describe how this gap was resolved" });
      return;
    }
    setSaving(true);
    try {
      fill(await api<KnowledgeGap>(url, { method: "PATCH", body: JSON.stringify({ status, notes, resolution }) }));
      setNotice({ tone: "success", text: "Knowledge gap updated." });
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields ?? {}).length > 0) setFieldErrors(apiErr.fields);
      else setNotice({ tone: "error", text: "We couldn't save your changes. Please try again." });
    } finally {
      setSaving(false);
    }
  }

  if (!isAdmin) {
    return (
      <AppShell>
        <PageHeader title="Knowledge gap" />
        <ErrorState message="You don't have permission to view knowledge gaps." />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <p>
        <Link to="/internal/knowledge-gaps">← Knowledge gaps</Link>
      </p>
      <PageHeader title="Knowledge gap" />
      {loadError ? (
        <ErrorState
          message={loadError.status === 404 ? "This knowledge gap is no longer available." : "We couldn't load this knowledge gap. Please try again."}
          onRetry={loadError.status === 404 ? undefined : load}
        />
      ) : !gap ? (
        <div className="pc-card">
          <Skeleton lines={5} />
        </div>
      ) : (
        <>
          <section className="pc-card" aria-labelledby="gap-question-heading">
            <h2 id="gap-question-heading" className="pc-card__title">
              Original question
            </h2>
            <p className="pc-gap__question">{gap.question}</p>
            <p className="pc-field__hint">
              {AUDIENCE_LABELS[gap.audience]} · asked {formatRelativeDay(gap.asked_at)}
              {gap.question_id && (
                <>
                  {" · "}
                  <Link to={`/internal/questions/${gap.question_id}`}>See what Policy Compass said</Link>
                </>
              )}
            </p>
            <h3 className="pc-answer__heading pc-answer__heading--small">Policies searched</h3>
            {gap.searched_policies.length === 0 ? (
              <p className="pc-field__hint">No related policies were found for this question.</p>
            ) : (
              <ul className="pc-gap__policies">
                {gap.searched_policies.map((p) => (
                  <li key={p.id}>
                    <Link to={`/internal/policies/${p.id}`}>{p.name}</Link>
                    {p.archived && <span className="pc-tag">Archived</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <form className="pc-card" onSubmit={save} noValidate aria-labelledby="gap-progress-heading">
            <h2 id="gap-progress-heading" className="pc-card__title">
              Progress
            </h2>
            {notice && <Alert tone={notice.tone} title={notice.text} />}
            <Select label="Status" options={STATUS_OPTIONS} value={status} onChange={(e) => setStatus(e.target.value as GapStatus)} />
            <Textarea
              label="Notes"
              hint="What you've found out or who is looking into it."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={2000}
              error={fieldErrors.notes}
            />
            <Textarea
              label="Resolution"
              hint="Required when resolving: for example, which policy was added or updated."
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              maxLength={2000}
              error={fieldErrors.resolution}
            />
            <p className="pc-field__hint">
              Tracking a gap doesn't change any policy. Upload or update the relevant policy, then resolve the gap.
            </p>
            <Button type="submit" loading={saving}>
              Save changes
            </Button>
          </form>
        </>
      )}
    </AppShell>
  );
}
