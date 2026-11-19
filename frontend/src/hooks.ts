import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/**
 * Load data and optionally refresh it every `intervalMs`. Polling (rather than
 * websockets) works behind the ALB with no sticky sessions: any instance can answer.
 * Pauses while the tab is hidden so idle tabs don't load the servers.
 */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh();
    if (!intervalMs) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, refresh, ...deps]);

  return { data, error, loading, refresh, setData };
}
