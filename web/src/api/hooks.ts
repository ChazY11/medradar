import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./client";

export type AsyncState<T> =
  | { status: "loading"; data: T | null; error: null }
  | { status: "error"; data: T | null; error: ApiError }
  | { status: "ready"; data: T; error: null };

export interface AsyncResult<T> {
  status: AsyncState<T>["status"];
  data: T | null;
  error: ApiError | null;
  reload: () => void;
}

/** Fetch once per dependency change, keeping the previous data while reloading. */
export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]): AsyncResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading", data: null, error: null });
  const [nonce, setNonce] = useState(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    setState((previous) => ({ status: "loading", data: previous.data, error: null }));
    loader()
      .then((data) => {
        if (!cancelled && alive.current) setState({ status: "ready", data, error: null });
      })
      .catch((error: unknown) => {
        if (cancelled || !alive.current) return;
        const apiError = error instanceof ApiError ? error : new ApiError(0, "unknown", String(error));
        setState({ status: "error", data: null, error: apiError });
      });
    return () => {
      cancelled = true;
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { status: state.status, data: state.data, error: state.error, reload };
}

export function useDebounced<T>(value: T, delayMs = 180): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [value, delayMs]);
  return debounced;
}

/** Reads a string from the URL query string with a fallback. */
export function useUrlParam(name: string, fallback = ""): string {
  const [value, setValue] = useState(() => new URLSearchParams(window.location.search).get(name) ?? fallback);
  useEffect(() => {
    const handler = () => {
      setValue(new URLSearchParams(window.location.search).get(name) ?? fallback);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [name, fallback]);
  return value;
}
