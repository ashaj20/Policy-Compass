import { useEffect, useState } from "react";
import { api } from "./api";
import { validateSlug } from "./slug";

export type SlugStatus =
  | { state: "idle" | "checking" | "current" }
  | { state: "available" }
  | { state: "unavailable"; message: string };

/**
 * Check a public URL is free shortly after the person stops typing.
 * `current` is the organisation's existing slug, which is always "yours" rather than taken.
 */
export function useSlugAvailability(slug: string, current?: string): SlugStatus {
  const [status, setStatus] = useState<SlugStatus>({ state: "idle" });

  useEffect(() => {
    if (!slug || validateSlug(slug)) {
      setStatus({ state: "idle" });
      return;
    }
    if (slug === current) {
      setStatus({ state: "current" });
      return;
    }
    setStatus({ state: "checking" });
    const timer = setTimeout(() => {
      api<{ available: boolean; message: string | null }>(
        `/organisations/slug-available?slug=${encodeURIComponent(slug)}`,
      )
        .then((r) => setStatus(r.available ? { state: "available" } : { state: "unavailable", message: r.message ?? "" }))
        .catch(() => setStatus({ state: "idle" }));
    }, 400);
    return () => clearTimeout(timer);
  }, [slug, current]);

  return status;
}
