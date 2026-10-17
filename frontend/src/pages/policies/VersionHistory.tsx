import { useRef, useState, type FormEvent } from "react";
import { Alert, Button, ConfirmDialog, Input, Modal } from "../../components";
import { FileDropzone } from "../../components/FileDropzone";
import { StatusBadge } from "../../components/StatusBadge";
import { api, ApiError, uploadWithProgress } from "../../lib/api";
import { formatFileSize, formatLongDate } from "../../lib/format";
import {
  POLICY_FILE_ACCEPT,
  validateEffectiveDate,
  validatePolicyFile,
  validateVersion,
  type PolicyVersion,
} from "../../lib/policy";
import { focusFirstError, hasErrors, type FieldErrors } from "../../lib/validation";

type Action =
  | { kind: "activate"; version: PolicyVersion }
  | { kind: "reject"; version: PolicyVersion }
  | { kind: "withdraw"; version: PolicyVersion };

interface VersionHistoryProps<T> {
  base: string;
  versions: PolicyVersion[];
  activeVersion?: PolicyVersion;
  isAdmin: boolean;
  userEmail: string;
  archived: boolean;
  onChanged: (policy: T, message: string) => void;
}

/**
 * Every version of a policy, newest first, with the review and approval actions that apply
 * (US-010A): any member marks a draft ready; administrators approve or send back; the person
 * who marked it ready, or an administrator, can withdraw it.
 */
export function VersionHistory<T>({
  base,
  versions,
  activeVersion,
  isAdmin,
  userEmail,
  archived,
  onChanged,
}: VersionHistoryProps<T>) {
  const [action, setAction] = useState<Action>();
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();

  async function run(version: PolicyVersion, step: "mark-ready" | "activate" | "withdraw" | "reject", body?: object) {
    setBusy(version.id + step);
    setError(undefined);
    try {
      const updated = await api<T>(`${base}/versions/${version.id}/${step}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      const messages = {
        "mark-ready": `Version ${version.version} is ready for an administrator's approval.`,
        activate: `Version ${version.version} is now active.`,
        withdraw: `Version ${version.version} is back in draft.`,
        reject: `Version ${version.version} has been sent back to draft.`,
      };
      setAction(undefined);
      onChanged(updated, messages[step]);
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <>
      {error && !action && <Alert tone="error" title={error} />}
      <ol className="pc-versions" aria-label="Versions, newest first">
        {versions.map((v) => {
          const canWithdraw = v.status === "READY" && (isAdmin || v.submitted_by === userEmail);
          return (
            <li key={v.id} className={`pc-versions__item ${v.status === "ACTIVE" ? "pc-versions__item--active" : ""}`}>
              <div className="pc-versions__head">
                <span className="pc-versions__label">Version {v.version}</span>
                <StatusBadge status={v.status} />
              </div>
              <p className="pc-versions__meta">
                Effective {formatLongDate(v.effective_date)} · {v.original_filename} ({formatFileSize(v.file_size)}) ·
                uploaded {formatLongDate(v.uploaded_at)}
                {v.uploaded_by ? ` by ${v.uploaded_by}` : ""}
              </p>
              <ul className="pc-versions__trail">
                {v.submitted_at && (
                  <li>
                    Marked ready {formatLongDate(v.submitted_at)}
                    {v.submitted_by ? ` by ${v.submitted_by}` : ""}
                  </li>
                )}
                {v.activated_at && (
                  <li>
                    Approved and activated {formatLongDate(v.activated_at)}
                    {v.activated_by ? ` by ${v.activated_by}` : ""}
                  </li>
                )}
                {v.superseded_at && (
                  <li>
                    Superseded {formatLongDate(v.superseded_at)}
                    {v.superseded_by ? ` by ${v.superseded_by}` : ""}
                  </li>
                )}
              </ul>
              {v.status === "DRAFT" && v.rejection_reason && (
                <Alert tone="warning" title="Sent back by an administrator">
                  <p>
                    “{v.rejection_reason}”{v.rejected_by ? ` (${v.rejected_by})` : ""}
                  </p>
                </Alert>
              )}
              {v.status === "FAILED" && (
                <p className="pc-field__error">This version couldn't be processed and will never replace the active version.</p>
              )}
              <div className="pc-versions__actions">
                <a className="pc-button pc-button--ghost" href={`/api${base}/versions/${v.id}/file`} download>
                  Download<span className="visually-hidden"> version {v.version}</span>
                </a>
                {!archived && v.status === "DRAFT" && (
                  <Button variant="secondary" loading={busy === v.id + "mark-ready"} onClick={() => run(v, "mark-ready")}>
                    Mark ready for approval
                  </Button>
                )}
                {!archived && v.status === "READY" && isAdmin && (
                  <>
                    <Button onClick={() => setAction({ kind: "activate", version: v })}>Approve &amp; activate</Button>
                    <Button variant="secondary" onClick={() => setAction({ kind: "reject", version: v })}>
                      Send back
                    </Button>
                  </>
                )}
                {!archived && canWithdraw && (
                  <Button variant="ghost" onClick={() => setAction({ kind: "withdraw", version: v })}>
                    Withdraw
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {action?.kind === "activate" && (
        <ConfirmDialog
          title={`Approve and activate version ${action.version.version}?`}
          message={
            <>
              <p>From now on, Policy Compass will use version {action.version.version} to answer questions.</p>
              {activeVersion ? (
                <p>
                  Version {activeVersion.version} will be marked Superseded and kept for history.
                </p>
              ) : (
                <p>This is the first version of this policy to go live.</p>
              )}
              <p className="pc-auth__muted">Your name and the time are recorded with this approval.</p>
            </>
          }
          confirmLabel="Approve & activate"
          onConfirm={() => run(action.version, "activate")}
          onCancel={() => setAction(undefined)}
          busy={busy === action.version.id + "activate"}
          error={error}
          destructive={false}
        />
      )}
      {action?.kind === "withdraw" && (
        <ConfirmDialog
          title={`Withdraw version ${action.version.version}?`}
          message={<p>It will go back to draft and will need to be marked ready again before it can be approved.</p>}
          confirmLabel="Withdraw"
          onConfirm={() => run(action.version, "withdraw")}
          onCancel={() => setAction(undefined)}
          busy={busy === action.version.id + "withdraw"}
          error={error}
          destructive={false}
        />
      )}
      {action?.kind === "reject" && (
        <RejectDialog
          version={action.version}
          busy={busy === action.version.id + "reject"}
          serverError={error}
          onCancel={() => setAction(undefined)}
          onReject={(reason) => run(action.version, "reject", { reason })}
        />
      )}
    </>
  );
}

function RejectDialog({
  version,
  busy,
  serverError,
  onCancel,
  onReject,
}: {
  version: PolicyVersion;
  busy: boolean;
  serverError?: string;
  onCancel: () => void;
  onReject: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim()) {
      setError("Say why this version is being sent back");
      return;
    }
    onReject(reason.trim());
  }

  return (
    <Modal
      title={`Send back version ${version.version}?`}
      onClose={onCancel}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" form="reject-form" loading={busy}>
            Send back to draft
          </Button>
        </>
      }
    >
      <p>It will return to draft. Your reason is shown on the policy and recorded in the activity history.</p>
      {serverError && <Alert tone="error" title={serverError} />}
      <form id="reject-form" onSubmit={onSubmit} noValidate>
        <Input
          label="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={error}
          maxLength={500}
          data-autofocus
        />
      </form>
    </Modal>
  );
}

/** Upload a new version alongside the active one (administrators). */
export function NewVersionDialog<T>({
  base,
  onClose,
  onUploaded,
}: {
  base: string;
  onClose: () => void;
  onUploaded: (policy: T) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [file, setFile] = useState<File>();
  const [version, setVersion] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [progress, setProgress] = useState<number>();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found = {
      file: file ? validatePolicyFile(file) : "Choose a PDF or Word document to upload",
      version: validateVersion(version),
      effective_date: validateEffectiveDate(effectiveDate),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    const body = new FormData();
    body.append("file", file!);
    body.append("version", version);
    body.append("effective_date", effectiveDate);
    setProgress(0);
    try {
      onUploaded(await uploadWithProgress<T>(`${base}/versions`, body, setProgress));
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) {
        setErrors(apiErr.fields);
        focusFirstError(formRef.current);
      } else {
        setFormError(apiErr.message);
      }
    } finally {
      setProgress(undefined);
    }
  }

  return (
    <Modal
      title="Upload new version"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={progress !== undefined}>
            Cancel
          </Button>
          <Button type="submit" form="new-version-form" loading={progress !== undefined}>
            {progress !== undefined ? `Uploading ${progress}%` : "Upload & process"}
          </Button>
        </>
      }
    >
      <p className="pc-auth__muted">
        The current active version stays in use until the new one has been processed, marked ready and approved.
      </p>
      {formError && <Alert tone="error" title={formError} />}
      <form id="new-version-form" ref={formRef} onSubmit={onSubmit} noValidate>
        <FileDropzone
          label="New document"
          accept={POLICY_FILE_ACCEPT}
          hint="PDF or Word (.docx), up to 20 MB."
          file={file}
          error={errors.file}
          onFile={(f) => {
            const problem = validatePolicyFile(f);
            setErrors((prev) => ({ ...prev, file: problem }));
            if (!problem) setFile(f);
          }}
          onClear={() => setFile(undefined)}
        />
        <Input label="Version" placeholder="e.g. 3.3" value={version} onChange={(e) => setVersion(e.target.value)} error={errors.version} />
        <Input
          label="Effective date"
          type="date"
          value={effectiveDate}
          onChange={(e) => setEffectiveDate(e.target.value)}
          error={errors.effective_date}
        />
      </form>
    </Modal>
  );
}
