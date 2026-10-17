import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Alert, AuthLayout, Button, Input } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { publicUrl, slugify, validateSlug } from "../../lib/slug";
import { focusFirstError, hasErrors, type FieldErrors } from "../../lib/validation";

const LOGO_MAX_BYTES = 2 * 1024 * 1024;
const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];

interface Organisation {
  id: string;
  slug: string;
}

type SlugStatus = { state: "idle" | "checking" } | { state: "available" } | { state: "unavailable"; message: string };

function validateName(value: string): string | undefined {
  const v = value.trim();
  if (!v) return "Enter your organisation's name";
  if (v.length < 2) return "Use at least 2 characters";
  if (v.length > 100) return "Use no more than 100 characters";
}

function validateWebsite(value: string): string | undefined {
  const v = value.trim();
  if (!v) return;
  const withScheme = v.includes("://") ? v : `https://${v}`;
  try {
    const url = new URL(withScheme);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".") || v.includes(" ")) throw new Error();
  } catch {
    return "Enter a valid website address, like https://www.organisation.org";
  }
}

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function CreateOrganisationPage() {
  const { user, refresh } = useAuth();
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [slugStatus, setSlugStatus] = useState<SlugStatus>({ state: "idle" });
  const [logo, setLogo] = useState<File>();
  const [logoPreview, setLogoPreview] = useState<string>();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  // Set once creation finishes, so the redirect below can carry the success message.
  const completed = useRef<{ notice?: string }>(undefined);

  // Check the public URL is free shortly after the person stops typing.
  useEffect(() => {
    if (!slug || validateSlug(slug)) {
      setSlugStatus({ state: "idle" });
      return;
    }
    setSlugStatus({ state: "checking" });
    const timer = setTimeout(() => {
      api<{ available: boolean; message: string | null }>(
        `/organisations/slug-available?slug=${encodeURIComponent(slug)}`,
      )
        .then((r) =>
          setSlugStatus(r.available ? { state: "available" } : { state: "unavailable", message: r.message ?? "" }),
        )
        .catch(() => setSlugStatus({ state: "idle" }));
    }, 400);
    return () => clearTimeout(timer);
  }, [slug]);

  useEffect(() => () => {
    if (logoPreview) URL.revokeObjectURL(logoPreview);
  }, [logoPreview]);

  if (currentMembership(user)) {
    const state = completed.current ? { created: true, notice: completed.current.notice } : undefined;
    return <Navigate to="/internal" replace state={state} />;
  }

  function onNameChange(value: string) {
    setName(value);
    if (!slugEdited) setSlug(slugify(value));
  }

  function onLogoChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) {
      setErrors((prev) => ({ ...prev, logo: "The logo must be a PNG, JPEG or WebP image." }));
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      setErrors((prev) => ({ ...prev, logo: "The logo must be 2 MB or smaller." }));
      return;
    }
    setErrors((prev) => ({ ...prev, logo: undefined }));
    setLogo(file);
    setLogoPreview(URL.createObjectURL(file));
  }

  function removeLogo() {
    setLogo(undefined);
    setLogoPreview(undefined);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found: FieldErrors = {
      name: validateName(name),
      website: validateWebsite(website),
      slug: validateSlug(slug) ?? (slugStatus.state === "unavailable" ? slugStatus.message : undefined),
      logo: errors.logo,
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);

    setSubmitting(true);
    let created: Organisation;
    try {
      created = await api<Organisation>("/organisations", {
        method: "POST",
        body: JSON.stringify({ name, slug, website }),
      });
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) {
        setErrors(apiErr.fields);
        focusFirstError(formRef.current);
      }
      if (apiErr.code !== "validation_error" && apiErr.code !== "slug_taken") setFormError(apiErr.message);
      setSubmitting(false);
      return;
    }

    let notice: string | undefined;
    if (logo) {
      const body = new FormData();
      body.append("file", logo);
      try {
        await api(`/organisations/${created.id}/logo`, { method: "PUT", body });
      } catch (err) {
        notice = `Your organisation was created, but the logo couldn't be uploaded: ${(err as ApiError).message} You can add it later in settings.`;
      }
    }
    // Reloading the user adds the new membership, which redirects to the workspace above.
    completed.current = { notice };
    await refresh();
  }

  const slugHintId = "slug-status";

  return (
    <AuthLayout title="Create your organisation" subtitle="This is your organisation's Policy Compass workspace.">
      <ol className="pc-steps" aria-label="Setup progress">
        <li className="pc-steps__item pc-steps__item--current" aria-current="step">
          <span className="pc-steps__number">1</span> Organisation
        </li>
        <li className="pc-steps__item">
          <span className="pc-steps__number">2</span> Policies
        </li>
        <li className="pc-steps__item">
          <span className="pc-steps__number">3</span> Ready
        </li>
      </ol>

      {formError && <Alert tone="error" title={formError} />}

      <form ref={formRef} onSubmit={onSubmit} noValidate className="pc-auth__form">
        <Input
          label="Organisation name"
          autoComplete="organization"
          placeholder="Riverside Housing"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          error={errors.name}
        />
        <Input
          label="Website (optional)"
          type="url"
          autoComplete="url"
          placeholder="https://www.riversidehousing.example"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          error={errors.website}
        />
        <Input
          label="Public URL"
          hint="Members of the public will use this address to ask questions. Lowercase letters, numbers and hyphens."
          autoCapitalize="none"
          spellCheck={false}
          value={slug}
          onChange={(e) => {
            setSlugEdited(true);
            setSlug(e.target.value.trim().toLowerCase());
          }}
          error={errors.slug}
          aria-describedby={slugHintId}
        />
        <div id={slugHintId} className="pc-slug-preview" aria-live="polite">
          {slug && !validateSlug(slug) && (
            <>
              <span className="pc-slug-preview__url">{publicUrl(slug)}</span>
              {slugStatus.state === "checking" && <span className="pc-slug-preview__status">Checking…</span>}
              {slugStatus.state === "available" && (
                <span className="pc-slug-preview__status pc-slug-preview__status--ok">✓ Available</span>
              )}
              {slugStatus.state === "unavailable" && (
                <span className="pc-slug-preview__status pc-slug-preview__status--bad">✕ {slugStatus.message}</span>
              )}
            </>
          )}
        </div>

        <fieldset className="pc-logo-picker">
          <legend className="pc-field__label">Logo (optional)</legend>
          <p className="pc-field__hint">PNG, JPEG or WebP, up to 2 MB.</p>
          {logo && logoPreview ? (
            <div className="pc-logo-picker__chosen">
              <img src={logoPreview} alt="Selected logo preview" className="pc-logo-picker__preview" />
              <div className="pc-logo-picker__meta">
                <span>{logo.name}</span>
                <span className="pc-field__hint">{formatSize(logo.size)}</span>
              </div>
              <Button variant="ghost" onClick={removeLogo}>
                Remove
              </Button>
            </div>
          ) : (
            <label className="pc-button pc-button--secondary pc-logo-picker__choose">
              Upload logo
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="visually-hidden"
                onChange={onLogoChange}
                aria-invalid={errors.logo ? true : undefined}
              />
            </label>
          )}
          {errors.logo && (
            <p className="pc-field__error" role="alert">
              <span aria-hidden="true">⚠ </span>
              {errors.logo}
            </p>
          )}
        </fieldset>

        <Button type="submit" loading={submitting} className="pc-auth__submit">
          {submitting ? "Creating organisation…" : "Create organisation"}
        </Button>
      </form>
    </AuthLayout>
  );
}
