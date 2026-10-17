import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert, AppShell, Button, ConfirmDialog, ErrorState, Input, Modal, PageHeader, Skeleton } from "../../components";
import { AudienceBadge } from "../../components/AudienceBadge";
import { RadioGroup } from "../../components/RadioGroup";
import { StatusBadge } from "../../components/StatusBadge";
import { VersionMeta } from "../../components/VersionMeta";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatFileSize, formatLongDate } from "../../lib/format";
import { usePolling } from "../../lib/polling";
import {
  AUDIENCE_OPTIONS,
  validateCategory,
  validatePolicyName,
  type Audience,
  type Policy,
  type PolicyVersion,
  type VersionStatus,
} from "../../lib/policy";
import { NewVersionDialog, VersionHistory } from "./VersionHistory";
import { focusFirstError, hasErrors, type FieldErrors } from "../../lib/validation";

interface PolicyDetail extends Policy {
  status: VersionStatus;
  version_count: number;
  current_version: PolicyVersion;
  active_version_id: string | null;
  versions: PolicyVersion[];
  archived_at: string | null;
  archived_by: string | null;
  owner: string | null;
  help_route: string | null;
}

/** Whether Policy Compass can use this policy to answer questions, in plain words. */
const KNOWLEDGE_STATUS: Record<VersionStatus, { icon: string; text: string; tone: string }> = {
  ACTIVE: { icon: "✓", text: "Available to Policy Compass", tone: "ok" },
  READY: { icon: "◷", text: "Ready – awaiting approval. Not yet used to answer questions.", tone: "info" },
  PROCESSING: { icon: "◐", text: "Processing. Not yet used to answer questions.", tone: "info" },
  DRAFT: {
    icon: "○",
    text: "Draft. It needs to be marked ready and approved before it is used to answer questions.",
    tone: "muted",
  },
  FAILED: { icon: "✕", text: "Processing failed. Not used to answer questions.", tone: "bad" },
  ARCHIVED: { icon: "▣", text: "Archived. No longer used to answer questions.", tone: "muted" },
  SUPERSEDED: { icon: "↺", text: "Superseded by a newer version.", tone: "muted" },
};

/** One policy's details (US-023). Administrators can edit; staff see ready policies read-only. */
export function PolicyDetailPage() {
  const { policyId = "" } = useParams();
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const base = `/organisations/${membership.organisation_id}/policies/${policyId}`;

  const [policy, setPolicy] = useState<PolicyDetail>();
  const [error, setError] = useState<ApiError>();
  const [editing, setEditing] = useState(false);
  const [uploadingVersion, setUploadingVersion] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [confirm, setConfirm] = useState<"archive" | "restore">();
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setPolicy(await api<PolicyDetail>(base));
    } catch (err) {
      setError(err as ApiError);
    }
  }, [base]);

  useEffect(() => {
    load();
  }, [load]);

  // Keep the page current while a version is being processed (US-012).
  const processing = policy?.versions.some((x) => x.status === "PROCESSING") ?? false;
  usePolling(async () => setPolicy(await api<PolicyDetail>(base)), processing);

  const back = (
    <Link to="/internal/policies" className="pc-back-link">
      ← Back to policies
    </Link>
  );

  if (error) {
    return (
      <AppShell>
        {back}
        <ErrorState
          message={error.status === 404 ? "This policy is no longer available." : "We couldn't load this policy. Please try again."}
          errorId={error.errorId}
          onRetry={error.status === 404 ? undefined : load}
        />
      </AppShell>
    );
  }

  if (!policy) {
    return (
      <AppShell>
        {back}
        <div className="pc-card">
          <Skeleton lines={8} />
        </div>
      </AppShell>
    );
  }

  async function onConfirm() {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError(undefined);
    try {
      setPolicy(await api<PolicyDetail>(`${base}/${confirm}`, { method: "POST" }));
      setNotice(confirm === "archive" ? "The policy has been archived." : "The policy has been restored.");
      setConfirm(undefined);
    } catch (err) {
      setConfirmError((err as ApiError).message);
    } finally {
      setConfirmBusy(false);
    }
  }

  const archived = Boolean(policy.archived_at);
  const v = policy.current_version;
  const activeVersion = policy.versions.find((x) => x.id === policy.active_version_id);
  const pending = policy.versions[0] && policy.versions[0].id !== policy.active_version_id ? policy.versions[0] : undefined;
  const knowledge = KNOWLEDGE_STATUS[policy.status];
  const showOwner = policy.audience !== "PUBLIC";
  const showHelpRoute = policy.audience !== "INTERNAL";

  return (
    <AppShell>
      {back}
      <PageHeader
        title={policy.name}
        actions={
          isAdmin && (
            <>
              {!archived && (
                <Button variant="ghost" onClick={() => setConfirm("archive")}>
                  Archive policy
                </Button>
              )}
              {!archived && (
                <Button variant="secondary" onClick={() => setUploadingVersion(true)}>
                  Upload new version
                </Button>
              )}
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit policy
              </Button>
            </>
          )
        }
      />
      <div className="pc-detail-badges">
        <StatusBadge status={policy.status} />
        <AudienceBadge audience={policy.audience} />
      </div>
      <VersionMeta version={v.version} effectiveDate={v.effective_date} updatedAt={policy.updated_at} />
      {notice && <Alert tone="success" title={notice} />}
      {archived && (
        <Alert
          tone="info"
          title="This policy is archived and is no longer used to answer questions."
          actions={
            isAdmin && (
              <Button variant="secondary" onClick={() => setConfirm("restore")}>
                Restore policy
              </Button>
            )
          }
        >
          <p>
            Archived {formatLongDate(policy.archived_at!)}
            {policy.archived_by ? ` by ${policy.archived_by}` : ""}.
          </p>
        </Alert>
      )}

      <section className="pc-card" aria-labelledby="knowledge-heading">
        <h2 id="knowledge-heading" className="pc-card__title">
          Knowledge status
        </h2>
        <p className={`pc-knowledge pc-knowledge--${knowledge.tone}`}>
          <span aria-hidden="true">{knowledge.icon}</span> {knowledge.text}
        </p>
        {activeVersion && !archived && (
          <p className="pc-auth__muted pc-auth__spaced">
            Answers use version {activeVersion.version}
            {activeVersion.activated_at ? `, approved ${formatLongDate(activeVersion.activated_at)}` : ""}
            {activeVersion.activated_by ? ` by ${activeVersion.activated_by}` : ""}.
            {pending && pending.status !== "FAILED" && ` Version ${pending.version} stays out of use until it is approved.`}
          </p>
        )}
      </section>

      <section className="pc-card" aria-labelledby="versions-heading">
        <h2 id="versions-heading" className="pc-card__title">
          Version history
        </h2>
        <VersionHistory<PolicyDetail>
          base={base}
          versions={policy.versions}
          activeVersion={activeVersion}
          isAdmin={isAdmin}
          userEmail={user?.email ?? ""}
          archived={archived}
          onChanged={(updated, message) => {
            setPolicy(updated);
            setNotice(message);
          }}
        />
      </section>

      <section className="pc-card" aria-labelledby="details-heading">
        <h2 id="details-heading" className="pc-card__title">
          Details
        </h2>
        <dl className="pc-summary pc-summary--inline">
          <div>
            <dt>Category</dt>
            <dd>{policy.category}</dd>
          </div>
          <div>
            <dt>Audience</dt>
            <dd>
              <AudienceBadge audience={policy.audience} />
            </dd>
          </div>
          <div>
            <dt>Version</dt>
            <dd>{v.version}</dd>
          </div>
          <div>
            <dt>Effective</dt>
            <dd>{formatLongDate(v.effective_date)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{policy.source ?? <span className="pc-auth__muted">Not recorded</span>}</dd>
          </div>
        </dl>
      </section>

      {(showOwner || showHelpRoute) && (
        <section className="pc-card" aria-labelledby="contacts-heading">
          <h2 id="contacts-heading" className="pc-card__title">
            Escalation
          </h2>
          <dl className="pc-summary pc-summary--inline">
            {showOwner && (
              <div>
                <dt>Policy owner</dt>
                <dd>{policy.owner ?? <span className="pc-auth__muted">Not assigned</span>}</dd>
              </div>
            )}
            {showHelpRoute && (
              <div>
                <dt>Public help route</dt>
                <dd>{policy.help_route ?? <span className="pc-auth__muted">Not assigned</span>}</dd>
              </div>
            )}
          </dl>
        </section>
      )}

      <section className="pc-card" aria-labelledby="document-heading">
        <h2 id="document-heading" className="pc-card__title">
          Document
        </h2>
        <div className="pc-document">
          <span className="pc-dropzone__icon" aria-hidden="true">
            📄
          </span>
          <div className="pc-dropzone__meta">
            <span className="pc-dropzone__name">{v.original_filename}</span>
            <span className="pc-field__hint">
              {formatFileSize(v.file_size)} · uploaded {formatLongDate(v.uploaded_at)}
              {v.uploaded_by ? ` by ${v.uploaded_by}` : ""}
            </span>
          </div>
          <a className="pc-button pc-button--secondary" href={`/api${base}/versions/${v.id}/file`} download>
            Download<span className="visually-hidden"> {v.original_filename}</span>
          </a>
        </div>
      </section>

      {confirm === "archive" && (
        <ConfirmDialog
          title="Archive this policy?"
          message={<p>Archived policies will no longer be used to answer questions.</p>}
          confirmLabel="Archive policy"
          onConfirm={onConfirm}
          onCancel={() => setConfirm(undefined)}
          busy={confirmBusy}
          error={confirmError}
        />
      )}
      {confirm === "restore" && (
        <ConfirmDialog
          title="Restore this policy?"
          message={<p>It will return to how it was before it was archived, including being used to answer questions if it was ready.</p>}
          confirmLabel="Restore policy"
          onConfirm={onConfirm}
          onCancel={() => setConfirm(undefined)}
          busy={confirmBusy}
          error={confirmError}
          destructive={false}
        />
      )}
      {uploadingVersion && (
        <NewVersionDialog<PolicyDetail>
          base={base}
          onClose={() => setUploadingVersion(false)}
          onUploaded={(updated) => {
            setPolicy(updated);
            setUploadingVersion(false);
            setNotice(`Version ${updated.versions[0]?.version} uploaded. It is being processed.`);
          }}
        />
      )}
      {editing && (
        <EditPolicyDialog
          policy={policy}
          base={base}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setPolicy(saved);
            setEditing(false);
            setNotice("Your changes have been saved.");
          }}
        />
      )}
    </AppShell>
  );
}

function EditPolicyDialog({
  policy,
  base,
  onClose,
  onSaved,
}: {
  policy: PolicyDetail;
  base: string;
  onClose: () => void;
  onSaved: (p: PolicyDetail) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState(policy.name);
  const [category, setCategory] = useState(policy.category);
  const [source, setSource] = useState(policy.source ?? "");
  const [audience, setAudience] = useState<Audience>(policy.audience);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [saving, setSaving] = useState(false);

  // Making internal content public is a security-relevant change, so call it out.
  const becomesPublic = policy.audience === "INTERNAL" && audience !== "INTERNAL";
  const becomesInternal = policy.audience !== "INTERNAL" && audience === "INTERNAL";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found = { name: validatePolicyName(name), category: validateCategory(category) };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    setSaving(true);
    try {
      onSaved(
        await api<PolicyDetail>(base, {
          method: "PATCH",
          body: JSON.stringify({ name, category, source, audience }),
        }),
      );
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) {
        setErrors(apiErr.fields);
        focusFirstError(formRef.current);
      } else {
        setFormError(apiErr.message);
      }
      setSaving(false);
    }
  }

  return (
    <Modal
      title="Edit policy"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-policy-form" loading={saving}>
            Save changes
          </Button>
        </>
      }
    >
      {formError && <Alert tone="error" title={formError} />}
      <form id="edit-policy-form" ref={formRef} onSubmit={onSubmit} noValidate>
        <Input label="Policy name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} data-autofocus />
        <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} error={errors.category} />
        <Input label="Source (optional)" value={source} onChange={(e) => setSource(e.target.value)} error={errors.source} />
        <RadioGroup
          legend="Audience"
          name="edit-audience"
          options={AUDIENCE_OPTIONS}
          value={audience}
          onChange={(value) => setAudience(value as Audience)}
          error={errors.audience}
        />
        {becomesPublic && (
          <Alert tone="warning" title="This policy will be used to answer public questions.">
            <p>Only make it public if everything in it is approved for customers and the public to see.</p>
          </Alert>
        )}
        {becomesInternal && (
          <Alert tone="info" title="This policy will no longer be used to answer public questions." />
        )}
      </form>
    </Modal>
  );
}
