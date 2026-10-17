import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, AppShell, Button, ErrorState, Input, PageHeader, Skeleton } from "../../components";
import { PublicPreview } from "../../components/PublicPreview";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { DEFAULT_BRAND, meetsContrast, normaliseHex } from "../../lib/colour";
import type { Organisation } from "../../lib/organisation";
import { LogoSection } from "./LogoSection";

/** Public branding (US-028): logo and primary colour, with a live preview of the public page. */
export function BrandingPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [org, setOrg] = useState<Organisation>();
  const [error, setError] = useState<ApiError>();
  const [colourText, setColourText] = useState(DEFAULT_BRAND);
  const [colourError, setColourError] = useState<string>();
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string }>();
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(undefined);
    try {
      const loaded = await api<Organisation>(`/organisations/${membership.organisation_id}`);
      setOrg(loaded);
      setColourText(loaded.primary_colour);
    } catch (err) {
      setError(err as ApiError);
    }
  }, [membership.organisation_id]);

  useEffect(() => {
    load();
  }, [load]);

  const colour = normaliseHex(colourText);
  const previewColour = colour ?? org?.primary_colour ?? DEFAULT_BRAND;
  const dirty = Boolean(org && colour && colour !== org.primary_colour);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setNotice(undefined);
    if (!colour) {
      setColourError("Enter a colour as a hex code, like #1f5aa6");
      return;
    }
    setColourError(undefined);
    setSaving(true);
    try {
      const saved = await api<Organisation>(`/organisations/${membership.organisation_id}`, {
        method: "PATCH",
        body: JSON.stringify({ primary_colour: colour }),
      });
      setOrg(saved);
      setColourText(saved.primary_colour);
      setNotice({ tone: "success", text: "Your branding has been saved." });
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.fields.primary_colour) setColourError(apiErr.fields.primary_colour);
      else setNotice({ tone: "error", text: apiErr.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <PageHeader title="Branding" description="How your public Policy Compass page and widget look to visitors." />
      {error ? (
        <ErrorState message="We couldn't load your branding. Please try again." errorId={error.errorId} onRetry={load} />
      ) : !org ? (
        <div className="pc-card">
          <Skeleton lines={6} />
        </div>
      ) : (
        <div className="pc-branding">
          <div className="pc-branding__controls">
            <LogoSection org={org} isAdmin={isAdmin} onChanged={setOrg} />
            <section className="pc-card" aria-labelledby="colour-heading">
              <h2 id="colour-heading" className="pc-card__title">
                Primary colour
              </h2>
              <p className="pc-auth__muted">Used for buttons and highlights on your public page.</p>
              {notice && <Alert tone={notice.tone} title={notice.text} />}
              {isAdmin ? (
                <form onSubmit={onSubmit} noValidate className="pc-settings-form pc-auth__spaced">
                  <div className="pc-colour-row">
                    <label className="pc-colour-swatch">
                      <span className="visually-hidden">Pick a colour</span>
                      <input type="color" value={previewColour} onChange={(e) => setColourText(e.target.value)} />
                    </label>
                    <Input
                      label="Hex code"
                      value={colourText}
                      onChange={(e) => setColourText(e.target.value)}
                      error={colourError}
                      spellCheck={false}
                      autoCapitalize="none"
                    />
                  </div>
                  {colour && !meetsContrast(colour) && (
                    <Alert tone="warning" title="This colour may be hard to read.">
                      <p>Text on buttons in this colour won't meet accessibility contrast guidelines. Try a darker or lighter shade.</p>
                    </Alert>
                  )}
                  <div className="pc-auth__spaced">
                    <Button type="submit" loading={saving} disabled={!dirty}>
                      Save changes
                    </Button>
                  </div>
                </form>
              ) : (
                <p>
                  <span className="pc-colour-chip" style={{ background: org.primary_colour }} aria-hidden="true" />{" "}
                  {org.primary_colour}
                </p>
              )}
            </section>
          </div>
          <section className="pc-card pc-branding__preview" aria-labelledby="preview-heading">
            <h2 id="preview-heading" className="pc-card__title">
              Public page preview
            </h2>
            <PublicPreview name={org.name} logoUrl={org.logo_url} colour={previewColour} />
          </section>
        </div>
      )}
    </AppShell>
  );
}