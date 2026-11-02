import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PauseCircle } from "lucide-react";
import { api } from "../api";
import { Badge, Progress } from "./ui";
import { fmtDuration, fmtSize } from "../format";
import type { QueueItem } from "../types";

// queue states that belong in the file column (failed/removed/imported fall back to the normal display)
const SHOWN = new Set(["grabbed", "queued", "downloading", "paused", "warning", "completed", "importing", "import_blocked"]);

/** Running downloads keyed by movie id and episode id. Updates live via the queue.updated SSE event. */
export function useDownloads() {
  const { data } = useQuery({ queryKey: ["queue"], queryFn: api.queue, refetchInterval: 30_000 });
  return useMemo(() => {
    const movies = new Map<number, QueueItem>();
    const episodes = new Map<number, QueueItem>();
    for (const q of data ?? []) {
      if (!SHOWN.has(q.status)) continue;
      if (q.movie_id) movies.set(q.movie_id, q);
      for (const e of q.episode_ids ?? []) episodes.set(e, q);
    }
    return { movies, episodes };
  }, [data]);
}

/** Two sheets of paper, one copying over to the other – shown while a download is imported. */
function CopyAnimation() {
  return (
    <svg className="copy-anim" width="26" height="16" viewBox="0 0 26 16" aria-hidden="true">
      <path d="M1.5 1.5h6l3 3v10h-9z" className="copy-doc" />
      <path d="M15.5 1.5h6l3 3v10h-9z" className="copy-doc" />
      <rect x="3" y="6" width="6" height="7" rx="1" className="copy-sheet" />
    </svg>
  );
}

export function DownloadStatus({ q, wide }: { q: QueueItem; wide?: boolean }) {
  const tip = `${q.title}${q.download_client ? `\n${q.download_client}` : ""}${q.messages?.length ? "\n" + q.messages.join("\n") : ""}`;
  if (q.status === "importing") {
    return (
      <span className="dl-status dl-importing" title={tip}>
        <CopyAnimation /> Importiere…
      </span>
    );
  }
  if (q.status === "import_blocked") {
    return (
      <Link to="/activity" className="dl-status" title={tip}>
        <Badge tone="warning">
          <AlertTriangle size={12} /> Import blockiert
        </Badge>
      </Link>
    );
  }
  const pct = q.status === "completed" ? 100 : q.progress || 0;
  const label =
    q.status === "completed" ? "fertig, Import folgt"
    : q.status === "paused" ? "pausiert"
    : q.status === "grabbed" || q.status === "queued" || (!pct && q.status !== "warning") ? "wartet"
    : `${pct.toFixed(pct < 10 ? 1 : 0)} %${q.eta_seconds ? ` · ${fmtDuration(q.eta_seconds)}` : ""}`;
  return (
    <span className={`dl-status dl-progress ${wide ? "wide" : ""}`} title={`${tip}\n${fmtSize(q.size - q.size_left)} von ${fmtSize(q.size)}`}>
      <Progress value={pct} small tone={q.status === "warning" ? "warning" : q.status === "paused" ? "muted" : "info"} />
      <span className="small muted nowrap">
        {q.status === "paused" && <PauseCircle size={11} />} {label}
      </span>
    </span>
  );
}
