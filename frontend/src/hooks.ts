import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, errorMessage } from "./api";
import { useToast } from "./components/Toast";
import { commandLabel } from "./format";
import { userCommandIds } from "./events";

// ------------------------------------------------------------------ shared reference data
export const useProfiles = () => useQuery({ queryKey: ["profiles"], queryFn: api.profiles, staleTime: 60_000 });
export const useRootFolders = () => useQuery({ queryKey: ["rootfolders"], queryFn: api.rootFolders, staleTime: 30_000 });
export const useTags = () => useQuery({ queryKey: ["tags"], queryFn: api.tags, staleTime: 60_000 });
export const useMovies = () => useQuery({ queryKey: ["movies"], queryFn: api.movies, staleTime: 30_000 });
export const useSeriesList = () => useQuery({ queryKey: ["series"], queryFn: api.seriesList, staleTime: 30_000 });
export const useQualities = () => useQuery({ queryKey: ["qualities"], queryFn: api.qualities, staleTime: Infinity });
export const useCustomFormats = () => useQuery({ queryKey: ["customformats"], queryFn: api.customFormats, staleTime: 60_000 });
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 30_000 });

/** POST /commands with a "gestartet" toast. */
export function useCommand() {
  const toast = useToast();
  const qc = useQueryClient();
  return useCallback(
    async (name: string, params?: Record<string, unknown>, label?: string) => {
      try {
        const c = await api.command(name, params);
        userCommandIds.add(c.id);
        toast.info(`${label ?? commandLabel(name)} gestartet`);
        qc.invalidateQueries({ queryKey: ["commands"] });
        return c;
      } catch (e) {
        toast.error(`${label ?? commandLabel(name)} fehlgeschlagen`, errorMessage(e));
        return null;
      }
    },
    [toast, qc],
  );
}

/** Mutation with error toast and automatic cache invalidation. */
export function useApiMutation<A, R>(
  fn: (a: A) => Promise<R>,
  opts: { invalidate?: QueryKey[]; success?: string | ((r: R, a: A) => string | null); onSuccess?: (r: R, a: A) => void; errorTitle?: string } = {},
) {
  const toast = useToast();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r, a) => {
      for (const k of opts.invalidate ?? []) qc.invalidateQueries({ queryKey: k });
      const msg = typeof opts.success === "function" ? opts.success(r, a) : opts.success;
      if (msg) toast.success(msg);
      opts.onSuccess?.(r, a);
    },
    onError: (e) => toast.error(opts.errorTitle ?? "Aktion fehlgeschlagen", errorMessage(e)),
  });
}

/** Re-render periodically (for relative times). */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(t);
  }, [intervalMs]);
  return now;
}

/** localStorage-backed state. */
export function useStored<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (nv: T) => {
      setV(nv);
      try {
        localStorage.setItem(key, JSON.stringify(nv));
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [v, set];
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}
