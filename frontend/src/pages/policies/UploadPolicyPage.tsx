import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, AppShell, Button, ErrorState, Input, PageHeader } from "../../components";
import { AudienceBadge } from "../../components/AudienceBadge";
import { FileDropzone } from "../../components/FileDropzone";
import { ProcessingSteps } from "../../components/ProcessingSteps";
import { RadioGroup } from "../../components/RadioGroup";
import { ContactPicker } from "../contacts/ContactPicker";
import type { Contacts } from "../../lib/contacts";
import { StatusBadge } from "../../components/StatusBadge";
import { VersionMeta } from "../../components/VersionMeta";
import { api, ApiError, uploadWithProgress } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import {
  AUDIENCE_OPTIONS,
  nameFromFilename,
  POLICY_FILE_ACCEPT,
  validateCategory,
  validateEffectiveDate,
  validatePolicyFile,
  validatePolicyName,
  validateVersion,
  type Audience,
  type Policy,
  type PolicyVersion,
} from "../../lib/policy";
import { usePolling } from "../../lib/polling";
import { focusFirstError, hasErrors, type FieldErrors } from "../../lib/validation";

/** Upload an approved policy document with its details (US-006). Administrators only. */
export function UploadPolicyPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const navigate = useNavigate();
  const base = `/organisations/${membership.organisation_id}/policies`;

  const formRef = useRef<HTMLFormElement>(null);
  const [file, setFile] = useState<File>();
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [version, setVersion] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [audience, setAudience] = useState<Audience | "">("");
  const [category, setCategory] = useState("");
  const [source, setSource] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [contacts, setContacts] = useState<Contacts>();
  const [ownerId, setOwnerId] = useState("");
  const [routeId, setRouteId] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [progress, setProgress] = useState<number>();
  const [uploaded, setUploaded] = useState<Policy>();

  const isAdmin = membership.role === "ADMIN";

  useEffect(() => {
    if (!isAdmin) return;
    api<string[]>(`${base}/categories`)
      .then(setCategories)
      .catch(() => setCategories([]));
    api<Contacts>(`/organisations/${membership.organisation_id}/contacts`)
      .then(setContacts)
      .catch(() => setContacts({ owners: [], help_routes: [] }));
  }, [base, isAdmin, membership.organisation_id]);

  // Follow processing after upload (US-012), until it finishes or fails.
  const [uploadedVersion, setUploadedVersion] = useState<PolicyVersion>();
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string>();
  const currentVersion = uploadedVersion ?? uploaded?.latest_version;
  usePolling(async () => {
    const detail = await api<{ versions: PolicyVersion[] }>(`${base}/${uploaded!.id}`);
    setUploadedVersion(detail.versions[0]);
  }, currentVersion?.status === "PROCESSING");

  async function retry() {
    if (!uploaded || !currentVersion) return;
    setRetrying(true);
    setRetryError(undefined);
    try {
      const detail = await api<{ versions: PolicyVersion[] }>(
        `${base}/${uploaded.id}/versions/${currentVersion.id}/retry`,
        { method: "POST" },
      );
      setUploadedVersion(detail.versions[0]);
    } catch (err) {
      setRetryError((err as ApiError).message);
    } finally {
      setRetrying(false);
    }
  }

  if (!isAdmin) {
    return (
      <AppShell>
        <PageHeader title="Upload policy" />
        <ErrorState message="You don't have permission to upload policies." />
      </AppShell>
    );
  }

  function chooseFile(chosen: File) {
    const problem = validatePolicyFile(chosen);
    setErrors((prev) => ({ ...prev, file: problem }));
    if (problem) return;
    setFile(chosen);
    if (!nameEdited) setName(nameFromFilename(chosen.name));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found: FieldErrors = {
      file: file ? validatePolicyFile(file) : "Choose a PDF or Word document to upload",
      name: validatePolicyName(name),
      version: validateVersion(version),
      effective_date: validateEffectiveDate(effectiveDate),
      audience: audience ? undefined : "Choose who this policy is for",
      category: validateCategory(category),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);

    const body = new FormData();
    body.append("file", file!);
    body.append("name", name);
    body.append("version", version);
    body.append("effective_date", effectiveDate);
    body.append("audience", audience);
    body.append("category", category);
    body.append("source", source);
    if ((audience === "INTERNAL" || audience === "BOTH") && ownerId) body.append("owner_id", ownerId);
    if ((audience === "PUBLIC" || audience === "BOTH") && routeId) body.append("help_route_id", routeId);

    setProgress(0);
    try {
      setUploaded(await uploadWithProgress<Policy>(base, body, setProgress));
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) {
        setErrors(apiErr.fields);
        focusFirstError(formRef.current);
      }
      if (!Object.keys(apiErr.fields).length || apiErr.code === "policy_exists") setFormError(apiErr.message);
    } finally {
      setProgress(undefined);
    }
  }

  function reset() {
    setUploaded(undefined);
    setUploadedVersion(undefined);
    setFile(undefined);
    setName("");
    setNameEdited(false);
    setVersion("");
    setEffectiveDate("");
    setAudience("");
    setCategory("");
    setSource("");
    setOwnerId("");
    setRouteId("");
    setErrors({});
  }

  if (uploaded && currentVersion) {
    const v = currentVersion;
    const actions = (
      <div className="pc-logo-setting__buttons">
        <Link to={`/internal/policies/${uploaded.id}`} className="pc-button pc-button--primary">
          View policy
        </Link>
        <Button variant="secondary" onClick={reset}>
          Upload another policy
        </Button>
        <Button variant="secondary" onClick={() => navigate("/internal/policies")}>
          Back to policies
        </Button>
      </div>
    );

    if (v.status === "FAILED") {
      return (
        <AppShell>
          <PageHeader title="Upload policy" />
          <section className="pc-card" aria-labelledby="upload-failed-title">
            <h2 id="upload-failed-title" className="pc-card__title">
              We couldn't process this policy
            </h2>
            <p className="pc-dropzone__name">{v.original_filename}</p>
            <ProcessingSteps stage={v.processing_stage} failed />
            <Alert tone="error" title={v.failure_reason ?? "Something went wrong while preparing this document for search."}>
              <p>Your original document has not been deleted.</p>
              {v.error_id && <p className="pc-state__ref">Reference: {v.error_id}</p>}
            </Alert>
            {retryError && <Alert tone="error" title={retryError} />}
            <div className="pc-logo-setting__buttons pc-auth__spaced">
              <Button onClick={retry} loading={retrying}>
                Retry processing
              </Button>
              <Button variant="secondary" onClick={() => navigate("/internal/policies")}>
                Back to policies
              </Button>
            </div>
          </section>
        </AppShell>
      );
    }

    const processing = v.status === "PROCESSING";
    return (
      <AppShell>
        <PageHeader title="Upload policy" />
        <section className="pc-card pc-upload-done" aria-labelledby="upload-done-title">
          <Alert
            tone="success"
            title={processing ? "Policy uploaded successfully." : "Processed and ready for review."}
          />
          <h2 id="upload-done-title" className="pc-card__title pc-auth__spaced">
            {uploaded.name}
          </h2>
          <VersionMeta version={v.version} effectiveDate={v.effective_date} updatedAt={uploaded.updated_at} />
          <dl className="pc-summary pc-summary--inline">
            <div>
              <dt>Document</dt>
              <dd>{v.original_filename}</dd>
            </div>
            <div>
              <dt>Audience</dt>
              <dd>
                <AudienceBadge audience={uploaded.audience} />
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <StatusBadge status={v.status} />
              </dd>
            </div>
          </dl>
          <div role="status" aria-live="polite">
            <h3 className="pc-upload__subheading">{processing ? "Processing policy" : "Processing complete"}</h3>
            <ProcessingSteps stage={v.processing_stage} />
            <p className="pc-auth__muted">
              {processing
                ? "This may take a few moments. It won't be used to answer questions until it has been processed, marked ready and approved by an administrator."
                : "Next, someone marks it ready for approval from the policy page, then an administrator approves it."}
            </p>
          </div>
          {actions}
        </section>
      </AppShell>
    );
  }
  const uploading = progress !== undefined;
  const showOwner = audience === "INTERNAL" || audience === "BOTH";
  const showHelpRoute = audience === "PUBLIC" || audience === "BOTH";

  return (
    <AppShell>
      <Link to="/internal/policies" className="pc-back-link">
        ← Back to policies
      </Link>
      <PageHeader title="Upload policy" description="Add an approved policy, procedure or guidance document." />
      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-upload">
        {formError && <Alert tone="error" title={formError} />}

        <section className="pc-card" aria-labelledby="upload-file-heading">
          <h2 id="upload-file-heading" className="pc-card__title">
            1. Document
          </h2>
          <FileDropzone
            label="Policy document"
            accept={POLICY_FILE_ACCEPT}
            hint="PDF or Word (.docx), up to 20 MB."
            file={file}
            error={errors.file}
            onFile={chooseFile}
            onClear={() => setFile(undefined)}
          />
        </section>

        <section className="pc-card" aria-labelledby="upload-details-heading">
          <h2 id="upload-details-heading" className="pc-card__title">
            2. Policy details
          </h2>
          <div className="pc-form-grid">
            <Input
              label="Policy name"
              value={name}
              onChange={(e) => {
                setNameEdited(true);
                setName(e.target.value);
              }}
              error={errors.name}
              className="pc-form-grid__full"
            />
            <Input
              label="Version"
              placeholder="e.g. 2.1"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              error={errors.version}
            />
            <Input
              label="Effective date"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              error={errors.effective_date}
            />
            <Input
              label="Category"
              placeholder="e.g. Repairs"
              list="policy-categories"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              error={errors.category}
            />
            <datalist id="policy-categories">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <Input
              label="Source (optional)"
              placeholder="e.g. Approved by the Board, August 2026"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              error={errors.source}
            />
          </div>
          <RadioGroup
            legend="Audience"
            name="audience"
            hint="Controls who Policy Compass can use this policy to answer."
            options={AUDIENCE_OPTIONS}
            value={audience}
            onChange={(v) => setAudience(v as Audience)}
            error={errors.audience}
          />

          {showOwner && (
            <ContactPicker
              kind="owner"
              options={contacts?.owners.map((o) => ({ value: o.id, label: o.job_title ? `${o.name} (${o.job_title})` : o.name })) ?? []}
              value={ownerId}
              onChange={setOwnerId}
              error={errors.owner_id}
            />
          )}
          {showHelpRoute && (
            <ContactPicker
              kind="route"
              options={contacts?.help_routes.map((r) => ({ value: r.id, label: r.is_default ? `${r.label} (default)` : r.label })) ?? []}
              value={routeId}
              onChange={setRouteId}
              error={errors.help_route_id}
            />
          )}
        </section>

        {uploading && (
          <div className="pc-progress" role="status" aria-live="polite">
            <div className="pc-progress__label">Uploading {progress}%</div>
            <div
              className="pc-progress__bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
              aria-label="Upload progress"
            >
              <span style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        <div className="pc-upload__actions">
          <Button variant="secondary" onClick={() => navigate("/internal/policies")} disabled={uploading}>
            Cancel
          </Button>
          <Button type="submit" loading={uploading}>
            Save &amp; process
          </Button>
        </div>
      </form>
    </AppShell>
  );
}
