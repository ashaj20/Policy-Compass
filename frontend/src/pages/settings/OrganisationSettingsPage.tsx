import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Alert, AppShell, Button, ConfirmDialog, ErrorState, Input, PageHeader, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import {
  LOGO_ACCEPT,
  validateLogo,
  validateOrganisationName,
  validateWebsite,
  type Organisation,
} from "../../lib/organisation";
import { publicUrl } from "../../lib/slug";
import { focusFirstError, hasErrors, type FieldErrors } from "../../lib/validation";

type Notice = { tone: "success" | "error"; text: string };

/** Organisation settings (US-004). Administrators edit; staff members see the details read-only. */
export function OrganisationSettingsPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [org, setOrg] = useState<Organisation>();
  const [loadError, setLoadError] = useState<ApiError>();

  const load = useCallback(async () => {
    setLoadError(undefined);
    try {
      setOrg(await api<Organisation>(`/organisations/${membership.organisation_id}`));
    } catch (err) {
      setLoadError(err as ApiError);
    }
  }, [membership.organisation_id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell>
      <PageHeader
        title="Organisation settings"
        description={
          isAdmin
            ? "Manage your organisation's details. These appear on your public Policy Compass page."
            : "Your organisation's details. Only administrators can change them."
        }
      />
      {loadError ? (
        <ErrorState message="We couldn't load your settings. Please try again." errorId={loadError.errorId} onRetry={load} />
      ) : !org ? (
        <div className="pc-card">
          <Skeleton lines={5} />
        </div>
      ) : (
        <>
          <DetailsSection org={org} isAdmin={isAdmin} onSaved={setOrg} />
          <LogoSection org={org} isAdmin={isAdmin} onChanged={setOrg} />
          <PublicUrlSection org={org} />
          {isAdmin && (
            <section className="pc-card" aria-labelledby="members-settings-heading">
              <h2 id="members-settings-heading" className="pc-card__title">
                Members
              </h2>
              <p className="pc-auth__muted">Invite people, change roles and remove access.</p>
              <Link to="/internal/settings/members" className="pc-button pc-button--secondary">
                Manage members
              </Link>
            </section>
          )}
        </>
      )}
    </AppShell>
  );
}

function DetailsSection({
  org,
  isAdmin,
  onSaved,
}: {
  org: Organisation;
  isAdmin: boolean;
  onSaved: (org: Organisation) => void;
}) {
  const { refresh } = useAuth();
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState(org.name);
  const [website, setWebsite] = useState(org.website ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [notice, setNotice] = useState<Notice>();
  const [saving, setSaving] = useState(false);

  const dirty = name !== org.name || website !== (org.website ?? "");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setNotice(undefined);
    const found = { name: validateOrganisationName(name), website: validateWebsite(website) };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    setSaving(true);
    try {
      const saved = await api<Organisation>(`/organisations/${org.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name, website }),
      });
      onSaved(saved);
      setName(saved.name);
      setWebsite(saved.website ?? "");
      setNotice({ tone: "success", text: "Your changes have been saved." });
      await refresh(); // the organisation name appears in the top bar
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) setErrors(apiErr.fields);
      else setNotice({ tone: "error", text: apiErr.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pc-card" aria-labelledby="details-heading">
      <h2 id="details-heading" className="pc-card__title">
        Organisation information
      </h2>
      {isAdmin ? (
        <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-settings-form">
          {notice && <Alert tone={notice.tone} title={notice.text} />}
          <Input
            label="Organisation name"
            autoComplete="organization"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={errors.name}
          />
          <Input
            label="Website (optional)"
            type="url"
            autoComplete="url"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            error={errors.website}
          />
          <div>
            <Button type="submit" loading={saving} disabled={!dirty}>
              Save changes
            </Button>
          </div>
        </form>
      ) : (
        <dl className="pc-summary">
          <div>
            <dt>Organisation name</dt>
            <dd>{org.name}</dd>
          </div>
          <div>
            <dt>Website</dt>
            <dd>{org.website ?? "Not set"}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function LogoSection({
  org,
  isAdmin,
  onChanged,
}: {
  org: Organisation;
  isAdmin: boolean;
  onChanged: (org: Organisation) => void;
}) {
  const [notice, setNotice] = useState<Notice>();
  const [uploading, setUploading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<string>();

  async function onFileChosen(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNotice(undefined);
    const problem = validateLogo(file);
    if (problem) {
      setNotice({ tone: "error", text: problem });
      return;
    }
    setUploading(true);
    const body = new FormData();
    body.append("file", file);
    try {
      onChanged(await api<Organisation>(`/organisations/${org.id}/logo`, { method: "PUT", body }));
      setNotice({ tone: "success", text: "Your logo has been updated." });
    } catch (err) {
      setNotice({ tone: "error", text: (err as ApiError).message });
    } finally {
      setUploading(false);
    }
  }

  async function onRemove() {
    setRemoving(true);
    setRemoveError(undefined);
    try {
      onChanged(await api<Organisation>(`/organisations/${org.id}/logo`, { method: "DELETE" }));
      setConfirmRemove(false);
      setNotice({ tone: "success", text: "Your logo has been removed." });
    } catch (err) {
      setRemoveError((err as ApiError).message);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <section className="pc-card" aria-labelledby="logo-heading">
      <h2 id="logo-heading" className="pc-card__title">
        Logo
      </h2>
      {notice && <Alert tone={notice.tone} title={notice.text} />}
      <div className="pc-logo-setting">
        <div className="pc-logo-setting__preview">
          {org.logo_url ? (
            <img src={org.logo_url} alt={`${org.name} logo`} />
          ) : (
            <span className="pc-auth__muted">No logo</span>
          )}
        </div>
        {isAdmin && (
          <div className="pc-logo-setting__actions">
            <p className="pc-field__hint">PNG, JPEG or WebP, up to 2 MB.</p>
            <div className="pc-logo-setting__buttons">
              <label className={`pc-button pc-button--secondary pc-logo-picker__choose ${uploading ? "is-busy" : ""}`}>
                {uploading ? "Uploading…" : org.logo_url ? "Upload new logo" : "Upload logo"}
                <input
                  type="file"
                  accept={LOGO_ACCEPT}
                  className="visually-hidden"
                  onChange={onFileChosen}
                  disabled={uploading}
                />
              </label>
              {org.logo_url && (
                <Button variant="ghost" onClick={() => setConfirmRemove(true)}>
                  Remove logo
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
      {confirmRemove && (
        <ConfirmDialog
          title="Remove your logo?"
          message={<p>Your public page will show your organisation's name without a logo.</p>}
          confirmLabel="Remove logo"
          onConfirm={onRemove}
          onCancel={() => setConfirmRemove(false)}
          busy={removing}
          error={removeError}
        />
      )}
    </section>
  );
}

function PublicUrlSection({ org }: { org: Organisation }) {
  const url = publicUrl(org.slug);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="pc-card" aria-labelledby="public-url-heading">
      <h2 id="public-url-heading" className="pc-card__title">
        Public URL
      </h2>
      <p className="pc-auth__muted">Members of the public use this address to ask questions about your policies.</p>
      <div className="pc-public-url">
        <a href={`/p/${org.slug}`} target="_blank" rel="noopener noreferrer" className="pc-public-url__link">
          {url}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
        <Button variant="secondary" onClick={copy}>
          Copy link
        </Button>
      </div>
      <p className="pc-field__hint" role="status">
        {copied ? "Link copied." : ""}
      </p>
    </section>
  );
}
