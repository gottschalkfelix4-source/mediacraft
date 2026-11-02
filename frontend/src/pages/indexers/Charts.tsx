import { useState } from "react";
import { fmtDateTime, fmtTime, parseDate } from "../../format";
import type { ForecastPoint, HistogramBucket } from "../../types";

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

const W = 900;
const PAD = { l: 40, r: 12, t: 14, b: 26 };

/** Hourly bar chart: queries vs grabs vs failed (hand-made SVG). */
export function UsageHistogram({ data }: { data: HistogramBucket[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const H = 240;
  const max = niceMax(Math.max(1, ...data.map((d) => Math.max(d.query, d.grab, d.failed))));
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const slot = iw / Math.max(1, data.length);
  const bw = Math.max(1.5, (slot - 2) / 3);
  const y = (v: number) => PAD.t + ih - (v / max) * ih;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * max));
  const labelEvery = data.length > 96 ? 24 : data.length > 48 ? 12 : 6;
  const h = hover !== null ? data[hover] : null;

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Anfragen pro Stunde" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={PAD.l - 6} y={y(t) + 4} className="chart-axis" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const x0 = PAD.l + i * slot + 1;
          const dt = parseDate(d.hour);
          return (
            <g key={d.hour} onMouseEnter={() => setHover(i)}>
              <rect x={x0 - 1} y={PAD.t} width={slot} height={ih} className={`chart-hover ${hover === i ? "on" : ""}`} />
              {d.query > 0 && <rect x={x0} y={y(d.query)} width={bw} height={Math.max(0, ih + PAD.t - y(d.query))} className="bar-query" rx={1} />}
              {d.grab > 0 && <rect x={x0 + bw} y={y(d.grab)} width={bw} height={Math.max(0, ih + PAD.t - y(d.grab))} className="bar-grab" rx={1} />}
              {d.failed > 0 && <rect x={x0 + 2 * bw} y={y(d.failed)} width={bw} height={Math.max(0, ih + PAD.t - y(d.failed))} className="bar-failed" rx={1} />}
              {dt && dt.getHours() % labelEvery === 0 && (
                <text x={x0 + slot / 2} y={H - 8} className="chart-axis" textAnchor="middle">
                  {dt.getHours() === 0 ? `${dt.getDate()}.${dt.getMonth() + 1}.` : fmtTime(dt)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.l} x2={W - PAD.r} y1={PAD.t + ih} y2={PAD.t + ih} className="chart-baseline" />
      </svg>
      <div className="chart-legend">
        <span className="lg-dot lg-query">Queries</span>
        <span className="lg-dot lg-grab">Grabs</span>
        <span className="lg-dot lg-failed">Fehlgeschlagen</span>
        <span className="chart-tip">
          {h ? (
            <>
              <strong>{fmtDateTime(h.hour)}</strong>: {h.query} Queries · {h.grab} Grabs · {h.failed} Fehler
            </>
          ) : (
            <span className="muted">Balken überfahren für Details</span>
          )}
        </span>
      </div>
    </div>
  );
}

/** Step chart: available units over the next hours. */
export function ForecastChart({ points, limit, reserve, label, tone }: { points: ForecastPoint[]; limit: number; reserve: number; label: string; tone: "query" | "grab" }) {
  const [hover, setHover] = useState<number | null>(null);
  const H = 200;
  const Wf = 440;
  const P = { l: 40, r: 10, t: 12, b: 24 };
  if (!limit || !points.length) {
    return (
      <div className="chart-wrap chart-empty">
        <div className="muted">{label}: kein Limit – Prognose nicht nötig</div>
      </div>
    );
  }
  const iw = Wf - P.l - P.r;
  const ih = H - P.t - P.b;
  const max = niceMax(limit);
  const t0 = parseDate(points[0].at)!.getTime();
  const t1 = parseDate(points[points.length - 1].at)!.getTime();
  const span = Math.max(1, t1 - t0);
  const x = (t: number) => P.l + ((t - t0) / span) * iw;
  const y = (v: number) => P.t + ih - (v / max) * ih;
  let d = "";
  points.forEach((p, i) => {
    const px = x(parseDate(p.at)!.getTime());
    const py = y(p.available);
    if (i === 0) d += `M${px},${py}`;
    else d += `H${px}V${py}`;
  });
  const area = `${d}V${y(0)}H${x(t0)}Z`;
  const ticks = [0, 0.5, 1].map((f) => Math.round(f * max));
  const hp = hover !== null ? points[hover] : null;
  return (
    <div className="chart-wrap">
      <div className="chart-title">{label}</div>
      <svg viewBox={`0 0 ${Wf} ${H}`} className="chart" role="img" aria-label={`Prognose ${label}`} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={Wf - P.r} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={P.l - 6} y={y(t) + 4} className="chart-axis" textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        <line x1={P.l} x2={Wf - P.r} y1={y(limit)} y2={y(limit)} className="chart-limit" />
        <text x={Wf - P.r} y={y(limit) - 4} className="chart-axis" textAnchor="end">
          Limit {limit}
        </text>
        {reserve > 0 && (
          <>
            <line x1={P.l} x2={Wf - P.r} y1={y(reserve)} y2={y(reserve)} className="chart-reserve" />
            <text x={Wf - P.r} y={y(reserve) - 4} className="chart-axis" textAnchor="end">
              Reserve {reserve}
            </text>
          </>
        )}
        <path d={area} className={`area-${tone}`} />
        <path d={d} className={`line-${tone}`} fill="none" />
        {points.map((p, i) => {
          const dt = parseDate(p.at)!;
          const px = x(dt.getTime());
          return (
            <g key={p.at} onMouseEnter={() => setHover(i)}>
              <rect x={px - iw / points.length / 2} y={P.t} width={iw / points.length} height={ih} fill="transparent" />
              {hover === i && <circle cx={px} cy={y(p.available)} r={4} className={`dot-${tone}`} />}
              {i % 6 === 0 && (
                <text x={px} y={H - 6} className="chart-axis" textAnchor="middle">
                  {i === 0 ? "jetzt" : `+${i} h`}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span className="chart-tip">
          {hp ? (
            <>
              <strong>{fmtDateTime(hp.at)}</strong>: {hp.available} verfügbar
            </>
          ) : (
            <span className="muted">Jetzt {points[0].available} verfügbar, in 24 h {points[points.length - 1].available}</span>
          )}
        </span>
      </div>
    </div>
  );
}
