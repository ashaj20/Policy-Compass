import { useEffect, useRef } from "react";

/** How often to refresh while something is processing. Tests shorten this. */
export const polling = { intervalMs: 2500 };

/**
 * Calls `refresh` repeatedly while `active` is true (e.g. a version is still processing),
 * and stops as soon as it isn't. Never runs two refreshes at once.
 */
export function usePolling(refresh: () => Promise<unknown>, active: boolean) {
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        await refreshRef.current();
      } catch {
        // A failed refresh is retried on the next tick; the page keeps its last good state.
      }
      if (!cancelled) timer = setTimeout(tick, polling.intervalMs);
    };
    timer = setTimeout(tick, polling.intervalMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [active]);
}
