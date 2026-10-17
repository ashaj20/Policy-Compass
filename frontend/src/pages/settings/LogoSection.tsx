import { useState, type ChangeEvent } from "react";
import { Alert, Button, ConfirmDialog } from "../../components";
import { api, ApiError } from "../../lib/api";
import { LOGO_ACCEPT, validateLogo, type Organisation } from "../../lib/organisation";

type Notice = { tone: "success" | "error"; text: string };

/** Upload, replace or remove the organisation's logo (US-002/004, shown under Branding). */
export function LogoSection({
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
