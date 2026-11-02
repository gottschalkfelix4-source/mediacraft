import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE } from "./api";
import { useToast } from "./components/Toast";
import { commandLabel } from "./format";
import type { SSEMessage } from "./types";

/** IDs of commands started from this UI (finished toasts are shown for these). */
export const userCommandIds = new Set<number>();

type Listener = (m: SSEMessage) => void;
const listeners = new Set<Listener>();

/** Subscribe to raw SSE messages from anywhere in the app. */
export function useEventListener(fn: Listener) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    const l: Listener = (m) => ref.current(m);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
}

/** Connects to /api/v1/events once and maps events onto react-query invalidations + toasts. */
export function useLiveEvents(enabled: boolean): boolean {
  const qc = useQueryClient();
  const toast = useToast();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const es = new EventSource(`${API_BASE}/events`, { withCredentials: true });
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => {
      let msg: SSEMessage;
      try {
        msg = JSON.parse(ev.data) as SSEMessage;
      } catch {
        return;
      }
      const t = msg.type || "";
      const id = msg.data?.id as number | undefined;
      if (t.startsWith("movie.")) {
        qc.invalidateQueries({ queryKey: ["movies"] });
        if (id) qc.invalidateQueries({ queryKey: ["movie", id] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["wanted"] });
        qc.invalidateQueries({ queryKey: ["calendar"] });
      } else if (t.startsWith("series.") || t.startsWith("episode")) {
        qc.invalidateQueries({ queryKey: ["series"] });
        if (id) {
          qc.invalidateQueries({ queryKey: ["series", id] });
          qc.invalidateQueries({ queryKey: ["episodes", id] });
        }
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["wanted"] });
        qc.invalidateQueries({ queryKey: ["calendar"] });
      } else if (t === "queue.updated" || t.startsWith("queue.")) {
        qc.invalidateQueries({ queryKey: ["queue"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
      } else if (t === "command.finished") {
        const name = String(msg.data?.name ?? "");
        const status = String(msg.data?.status ?? "");
        qc.invalidateQueries({ queryKey: ["commands"] });
        qc.invalidateQueries({ queryKey: ["tasks"] });
        const silent = /check_downloads|health_check|housekeeping/.test(name);
        // a command may have changed a lot – refresh the usual suspects
        const keys = silent
          ? ["queue", "history", "dashboard", "health"]
          : ["movies", "series", "movie", "episodes", "queue", "history", "dashboard", "wanted", "health", "indexers", "indexers-usage", "indexer-usage", "blocklist"];
        for (const k of keys) qc.invalidateQueries({ queryKey: [k] });
        const mine = userCommandIds.has(Number(msg.data?.id));
        userCommandIds.delete(Number(msg.data?.id));
        const scheduled = name.startsWith("task:") && !mine;
        if (status === "failed" && (!scheduled || !silent)) toast.error(`${commandLabel(name)} fehlgeschlagen`, String(msg.data?.error ?? ""));
        else if (status !== "failed" && (mine || (!silent && !scheduled))) toast.success(`${commandLabel(name)} abgeschlossen`);
      } else if (t.startsWith("command.")) {
        qc.invalidateQueries({ queryKey: ["commands"] });
        qc.invalidateQueries({ queryKey: ["tasks"] });
      } else if (t.startsWith("indexer")) {
        qc.invalidateQueries({ queryKey: ["indexers"] });
        qc.invalidateQueries({ queryKey: ["indexers-usage"] });
      } else if (t.startsWith("history") || t.startsWith("download") || t.startsWith("import")) {
        qc.invalidateQueries({ queryKey: ["history"] });
        qc.invalidateQueries({ queryKey: ["queue"] });
      }
      listeners.forEach((l) => l(msg));
    };
    return () => {
      es.close();
      setConnected(false);
    };
  }, [enabled, qc, toast]);

  return connected;
}
