import { Clock, Globe } from "lucide-react";
import { fmtDateTime, relTime, parseDate } from "../format";
import type { LimitState } from "../types";

const KIND_LABEL = { query: "Queries", grab: "Grabs" } as const;

export function windowLabel(mode: string, hours: number, resetHour?: number | null): string {
  const h = hours || 24;
  const span = h % 24 === 0 && h >= 48 ? `${h / 24} Tage` : `${h} h`;
  if (mode === "fixed") {
    const rh = String(resetHour ?? 0).padStart(2, "0");
    return h > 24 ? `fester Reset alle ${span} um ${rh}:00 UTC` : `fester Reset ${rh}:00 UTC`;
  }
  return `rollierend ${span}`;
}

function tone(st: LimitState): string {
  if (!st.limit) return "muted";
  if (st.used >= st.limit) return "danger";
  if (st.reserve && st.used >= st.limit - st.reserve) return "warning";
  if (st.percent >= 80) return "warning";
  return "accent";
}

/** Usage bar for one limit (query or grab) incl. reserve marker and next free slot. */
export function UsageMeter({ st, now, compact, showWindow, mode, hours, resetHour }: {
  st: LimitState;
  now: Date;
  compact?: boolean;
  showWindow?: boolean;
  mode?: string;
  hours?: number;
  resetHour?: number;
}) {
  const label = KIND_LABEL[st.kind] ?? st.kind;
  if (!st.limit) {
    return (
      <div className={`usage ${compact ? "usage-compact" : ""}`}>
        <div className="usage-head">
          <span className="usage-label">{label}</span>
          <span className="usage-nums">
            {st.used.toLocaleString("de-DE")} <span className="muted">/ ∞</span>
          </span>
        </div>
        <div className="progress progress-sm unlimited" title="Kein Limit konfiguriert">
          <div className="progress-bar tone-muted" style={{ width: "100%" }} />
        </div>
        {!compact && <div className="usage-meta muted">Unbegrenzt{st.remote_used != null && ` · Indexer meldet ${st.remote_used}`}</div>}
      </div>
    );
  }
  const pct = Math.min(100, st.percent);
  const reservePct = st.reserve ? (100 * (st.limit - st.reserve)) / st.limit : null;
  const nextSlot = parseDate(st.next_slot);
  const exhausted = st.used >= st.limit;
  const autoExhausted = !exhausted && st.reserve > 0 && st.used >= st.limit - st.reserve;
  const t = tone(st);
  return (
    <div className={`usage ${compact ? "usage-compact" : ""}`}>
      <div className="usage-head">
        <span className="usage-label">{label}</span>
        <span className={`usage-nums tone-text-${t}`}>
          {st.used.toLocaleString("de-DE")} / {st.limit.toLocaleString("de-DE")}
          <span className="muted"> · {st.percent.toLocaleString("de-DE", { maximumFractionDigits: 1 })} %</span>
        </span>
      </div>
      <div
        className="progress"
        title={`${st.used} von ${st.limit} verbraucht${st.reserve ? `, Reserve ${st.reserve} für manuelle Aktionen` : ""}`}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`progress-bar tone-${t}`} style={{ width: `${pct}%` }} />
        {reservePct !== null && reservePct > 0 && reservePct < 100 && (
          <>
            <div className="progress-reserve" style={{ left: `${reservePct}%` }} />
            <div className="progress-marker" style={{ left: `${reservePct}%` }} title={`Reserve: letzte ${st.reserve} nur manuell`} />
          </>
        )}
      </div>
      <div className="usage-meta">
        <span>
          Rest <strong>{st.remaining ?? "–"}</strong>
          {st.reserve > 0 && (
            <span className="muted">
              {" "}
              (auto {st.remaining_auto ?? 0}, Reserve {st.reserve})
            </span>
          )}
        </span>
        {st.remote_used != null && (
          <span className="muted" title="Vom Indexer gemeldeter Zähler (newznab:apilimits)">
            <Globe size={12} /> Indexer: {st.remote_used}
          </span>
        )}
        {nextSlot && (exhausted || autoExhausted) && (
          <span className={exhausted ? "tone-text-danger" : "tone-text-warning"} title={fmtDateTime(nextSlot)}>
            <Clock size={12} /> {exhausted ? "Nächster Slot" : "Auto wieder"} {relTime(nextSlot, now)}
          </span>
        )}
        {!compact && st.window_end && !nextSlot && (
          <span className="muted" title={fmtDateTime(st.window_end)}>
            <Clock size={12} /> Reset {relTime(st.window_end, now)}
          </span>
        )}
        {showWindow && mode && <span className="muted">{windowLabel(mode, hours ?? 24, resetHour)}</span>}
      </div>
    </div>
  );
}
