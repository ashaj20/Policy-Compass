import { publicUrl, validateSlug } from "../lib/slug";
import type { SlugStatus } from "../lib/useSlugAvailability";

/** Full public address and live availability under a slug field. Announced politely. */
export function SlugPreview({ id, slug, status }: { id: string; slug: string; status: SlugStatus }) {
  return (
    <div id={id} className="pc-slug-preview" aria-live="polite">
      {slug && !validateSlug(slug) && (
        <>
          <span className="pc-slug-preview__url">{publicUrl(slug)}</span>
          {status.state === "checking" && <span className="pc-slug-preview__status">Checking…</span>}
          {status.state === "current" && <span className="pc-slug-preview__status">Your current URL</span>}
          {status.state === "available" && (
            <span className="pc-slug-preview__status pc-slug-preview__status--ok">✓ Available</span>
          )}
          {status.state === "unavailable" && (
            <span className="pc-slug-preview__status pc-slug-preview__status--bad">✕ {status.message}</span>
          )}
        </>
      )}
    </div>
  );
}
