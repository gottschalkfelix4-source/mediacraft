import { useState, type ReactNode } from "react";
import { Film, Tv, Star } from "lucide-react";
import { providerLabel } from "../format";
import type { Rating, Tag } from "../types";

/** Lazy-loaded poster image with graceful fallback. */
export function Poster({ src, title, kind = "movie", className }: { src?: string | null; title: string; kind?: "movie" | "series"; className?: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  if (!src || failed) {
    const Icon = kind === "movie" ? Film : Tv;
    return (
      <div className={`poster poster-fallback ${className ?? ""}`} aria-label={title}>
        <Icon size={28} />
        <span>{title}</span>
      </div>
    );
  }
  return (
    <div className={`poster ${loaded ? "loaded" : ""} ${className ?? ""}`}>
      <img src={src} alt={title} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} onLoad={() => setLoaded(true)} />
    </div>
  );
}

export function SourceBadges({ sources }: { sources?: (string | null | undefined)[] | null }) {
  const list = (sources ?? []).filter((s): s is string => !!s);
  if (!list.length) return null;
  return (
    <span className="source-badges" title="Metadaten-Quellen">
      {list.map((s, i) => (
        <span key={`${s}-${i}`} className={`src-badge src-${s} ${i === 0 ? "primary" : ""}`} title={i === 0 ? "Primärquelle" : "Ergänzende Quelle"}>
          {providerLabel(s)}
        </span>
      ))}
    </span>
  );
}

const RATING_LABELS: Record<string, string> = { tmdb: "TMDB", imdb: "IMDb", tvdb: "TVDB", tvmaze: "TVmaze", anilist: "AniList", metacritic: "Metacritic", rottenTomatoes: "RT", rotten_tomatoes: "RT", omdb: "OMDb" };

export function Ratings({ ratings }: { ratings?: Record<string, Rating> | null }) {
  const entries = Object.entries(ratings ?? {}).filter(([, r]) => r && r.value);
  if (!entries.length) return null;
  return (
    <div className="ratings">
      {entries.map(([k, r]) => (
        <span key={k} className="rating" title={r.votes ? `${r.votes.toLocaleString("de-DE")} Stimmen` : undefined}>
          <Star size={13} /> <strong>{RATING_LABELS[k] ?? k}</strong> {Number(r.value).toLocaleString("de-DE", { maximumFractionDigits: 1 })}
        </span>
      ))}
    </div>
  );
}

export function TagList({ ids, tags }: { ids: number[]; tags?: Tag[] }) {
  if (!ids?.length) return null;
  return (
    <span className="tag-list">
      {ids.map((id) => (
        <span className="tag" key={id}>
          {tags?.find((t) => t.id === id)?.label ?? `#${id}`}
        </span>
      ))}
    </span>
  );
}

export function Fanart({ src, children }: { src?: string | null; children: ReactNode }) {
  return (
    <div className="detail-hero">
      {src && <div className="detail-hero-bg" style={{ backgroundImage: `url("${src}")` }} />}
      <div className="detail-hero-shade" />
      <div className="detail-hero-content">{children}</div>
    </div>
  );
}
