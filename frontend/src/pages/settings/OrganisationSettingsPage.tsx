import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Alert, AppShell, Button, ConfirmDialog, ErrorState, Input, PageHeader, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import {
  validateOrganisationName,
  validateWebsite,
  type Organisation,
} from "../../lib/organisation";
import { SlugPreview } from "../../components/SlugPreview";
import { publicUrl, validateSlug } from "../../lib/slug";
import { useSlugAvailability } from "../../lib/useSlugAvailability";
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
          <PublicUrlSection org={org} isAdmin={isAdmin} onChanged={setOrg} />
          <section className="pc-card" aria-labelledby="branding-settings-heading">
            <h2 id="branding-settings-heading" className="pc-card__title">
              Logo and colours
            </h2>
            <p className="pc-auth__muted">Your logo and primary colour are managed under Branding.</p>
            {isAdmin && (
              <Link to="/internal/settings/branding" className="pc-button pc-button--secondary">
                Go to branding
              </Link>
            )}
          </section>
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

function PublicUrlSection({
  org,
  isAdmin,
  onChanged,
}: {
  org: Organisation;
  isAdmin: boolean;
  onChanged: (org: Organisation) => void;
}) {
  const { refresh } = useAuth();
  const url = publicUrl(org.slug);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [slug, setSlug] = useState(org.slug);
  const [error, setError] = useState<string>();
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice>();
  const status = useSlugAvailability(editing ? slug : "", org.slug);
  const inputRef = useRef<HTMLFormElement>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function startEditing() {
    setNotice(undefined);
    setSlug(org.slug);
    setError(undefined);
    setEditing(true);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem =
      validateSlug(slug) ??
      (slug === org.slug ? "Enter a different URL to change it" : undefined) ??
      (status.state === "unavailable" ? status.message : undefined);
    setError(problem);
    if (problem) return focusFirstError(inputRef.current);
    setConfirming(true);
  }

  async function onConfirm() {
    setSaving(true);
    try {
      const saved = await api<Organisation>(`/organisations/${org.id}/slug`, {
        method: "PUT",
        body: JSON.stringify({ slug }),
      });
      onChanged(saved);
      setConfirming(false);
      setEditing(false);
      setNotice({ tone: "success", text: "Your public URL has been changed." });
      await refresh();
    } catch (err) {
      const apiErr = err as ApiError;
      setConfirming(false);
      setError(apiErr.fields.slug ?? apiErr.message);
      focusFirstError(inputRef.current);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pc-card" aria-labelledby="public-url-heading">
      <h2 id="public-url-heading" className="pc-card__title">
        Public URL
      </h2>
      {notice && <Alert tone={notice.tone} title={notice.text} />}
      <p className="pc-auth__muted">Members of the public use this address to ask questions about your policies.</p>

      {editing ? (
        <form ref={inputRef} onSubmit={onSubmit} noValidate className="pc-settings-form pc-auth__spaced">
          <Input
            label="New public URL"
            hint="Lowercase letters, numbers and hyphens."
            autoCapitalize="none"
            spellCheck={false}
            value={slug}
            onChange={(e) => setSlug(e.target.value.trim().toLowerCase())}
            error={error}
            aria-describedby="new-slug-status"
            autoFocus
          />
          <SlugPreview id="new-slug-status" slug={slug} status={status} />
          <div className="pc-logo-setting__buttons">
            <Button type="submit">Change URL</Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          <div className="pc-public-url">
            <a href={`/p/${org.slug}`} target="_blank" rel="noopener noreferrer" className="pc-public-url__link">
              {url}
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
            <Button variant="secondary" onClick={copy}>
              Copy link
            </Button>
            {isAdmin && (
              <Button variant="ghost" onClick={startEditing}>
                Change URL
              </Button>
            )}
          </div>
          <p className="pc-field__hint" role="status">
            {copied ? "Link copied." : ""}
          </p>
        </>
      )}

      {confirming && (
        <ConfirmDialog
          title="Change your public URL?"
          message={
            <>
              <p>Changing your public URL may break existing links.</p>
              <p className="pc-auth__muted">
                New address: <strong>{publicUrl(slug)}</strong>. The old address will stop working, including any
                links or embedded widgets that use it.
              </p>
            </>
          }
          confirmLabel="Change URL"
          onConfirm={onConfirm}
          onCancel={() => setConfirming(false)}
          busy={saving}
          destructive={false}
        />
      )}
    </section>
  );
}