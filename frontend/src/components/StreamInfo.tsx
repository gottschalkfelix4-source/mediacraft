import { AlertTriangle } from "lucide-react";
import { langLabel } from "../format";
import { Badge } from "./ui";
import type { MediaFile } from "../types";

interface Probe {
  video_codec?: string;
  width?: number;
  height?: number;
  resolution?: number;
  hdr?: string | null;
  audio_tracks?: { codec?: string; channels?: number; language?: string; title?: string }[];
  audio_languages?: string[];
  subtitle_languages?: string[];
  duration_min?: number;
  bitrate_kbps?: number;
}

function channels(n?: number) {
  if (!n) return "";
  return n === 6 ? "5.1" : n === 8 ? "7.1" : n === 2 ? "2.0" : `${n}ch`;
}

export function probeOf(f: MediaFile): Probe | null {
  return ((f.media_info ?? {}) as { probe?: Probe }).probe ?? null;
}

export function languageMismatch(f: MediaFile): string[] | null {
  return ((f.media_info ?? {}) as { language_mismatch?: string[] }).language_mismatch ?? null;
}

/** Key/value rows with the real stream info of a file (from ffprobe/MediaInfo). */
export function streamRows(f: MediaFile): [string, React.ReactNode][] {
  const p = probeOf(f);
  const mismatch = languageMismatch(f);
  const rows: [string, React.ReactNode][] = [];
  if (mismatch)
    rows.push([
      "Hinweis",
      <span className="tone-text-warning">
        <AlertTriangle size={13} /> Laut Release {mismatch.map(langLabel).join("/")}, die Datei enthält aber {p?.audio_languages?.map(langLabel).join(", ") || "keine erkennbare Sprache"}
      </span>,
    ]);
  if (!p) return rows;
  rows.push([
    "Video",
    <>
      {p.width && p.height ? `${p.width}×${p.height}` : ""} {p.video_codec} {p.hdr && <Badge tone="accent">{p.hdr}</Badge>}
      {p.bitrate_kbps ? <span className="muted small"> · {(p.bitrate_kbps / 1000).toFixed(1)} Mbit/s</span> : null}
    </>,
  ]);
  rows.push([
    "Tonspuren",
    (p.audio_tracks ?? []).length
      ? (p.audio_tracks ?? []).map((a, i) => (
          <Badge key={i} tone="muted">
            {a.language ? a.language.toUpperCase() : "?"} · {a.codec} {channels(a.channels)}
          </Badge>
        ))
      : "–",
  ]);
  if (p.subtitle_languages?.length) rows.push(["Untertitel", p.subtitle_languages.join(", ")]);
  if (p.duration_min) rows.push(["Laufzeit", `${Math.round(p.duration_min)} min`]);
  return rows;
}
