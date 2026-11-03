import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Film, HardDrive, Tv } from "lucide-react";
import { api } from "../api";
import { Card, ErrorBox, Loading, PageHeader, Select } from "../components/ui";
import { fmtDate, fmtNumber, fmtSize, langLabel } from "../format";
import type { StatsBucket, StatsData } from "../types";

/** Horizontal bars, one hue: magnitude only. The value is written next to every bar, so no axis is needed. */
function BarList({ rows, value, format, label }: { rows: StatsBucket[]; value: (r: StatsBucket) => number; format: (r: StatsBucket) => string; label?: (n: string) => string }) {
  const max = Math.max(1, ...rows.map(value));
  if (!rows.length) return <p className="muted">Keine Daten.</p>;
  return (
    <div className="barlist" role="table">
      {rows.map((r) => (
        <div className="barlist-row" role="row" key={r.name} title={`${label ? label(r.name) : r.name}: ${format(r)}`}>
          <span className="barlist-label" role="cell">
            {label ? label(r.name) : r.name}
          </span>
          <span className="barlist-track" role="cell" aria-hidden>
            <span className="barlist-fill" style={{ width: `${(100 * value(r)) / max}%` }} />
          </span>
          <span className="barlist-value" role="cell">
            {format(r)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Columns per week, one series at a time (no dual axis); hover shows the exact value. */
function WeekColumns({ weeks, metric }: { weeks: StatsData["weeks"]; metric: "grabs" | "imports" | "failed" }) {
  const max = Math.max(1, ...weeks.map((w) => w[metric]));
  return (
    <div className="weekcols" role="img" aria-label="Verlauf pro Woche">
      {weeks.map((w) => (
        <div className="weekcol" key={w.week} data-tip={`Woche ab ${fmtDate(w.week)}: ${fmtNumber(w[metric])}`}>
          <span className="weekcol-bar" style={{ height: `${(100 * w[metric]) / max}%` }} />
          <span className="weekcol-label">{fmtDate(w.week).slice(0, 6)}</span>
        </div>
      ))}
    </div>
  );
}

const METRICS = { grabs: "Grabs", imports: "Importe", failed: "Fehlgeschlagen" } as const;

export function StatsPage() {
  const [weeks, setWeeks] = useState(12);
  const [metric, setMetric] = useState<keyof typeof METRICS>("grabs");
  const { data, isLoading, error } = useQuery({ queryKey: ["stats", weeks], queryFn: () => api.stats(weeks), staleTime: 60_000 });

  return (
    <div className="page">
      <PageHeader title="Statistik">
        <Select
          value={weeks}
          onValue={setWeeks}
          aria-label="Zeitraum"
          options={[
            { value: 4, label: "4 Wochen" },
            { value: 12, label: "12 Wochen" },
            { value: 26, label: "26 Wochen" },
            { value: 52, label: "52 Wochen" },
          ]}
        />
      </PageHeader>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <Film size={22} className="stat-icon" />
              <div>
                <div className="stat-value">{fmtNumber(data.library.movies)}</div>
                <div className="stat-label">Filme</div>
                <div className="stat-sub">
                  {fmtNumber(data.library.movies_with_file)} vorhanden · {fmtSize(data.library.movie_size)}
                </div>
              </div>
            </div>
            <div className="stat">
              <Tv size={22} className="stat-icon" />
              <div>
                <div className="stat-value">{fmtNumber(data.library.series)}</div>
                <div className="stat-label">Serien</div>
                <div className="stat-sub">
                  {fmtNumber(data.library.episodes_with_file)}/{fmtNumber(data.library.episodes)} Episoden · {fmtSize(data.library.episode_size)}
                </div>
              </div>
            </div>
            <div className="stat">
              <HardDrive size={22} className="stat-icon" />
              <div>
                <div className="stat-value">{fmtSize(data.library.total_size)}</div>
                <div className="stat-label">Bibliothek</div>
                <div className="stat-sub">{fmtNumber(data.library.files)} Dateien</div>
              </div>
            </div>
            <div className="stat">
              <BarChart3 size={22} className="stat-icon" />
              <div>
                <div className="stat-value">{fmtNumber(data.weeks.reduce((n, w) => n + w.grabs, 0))}</div>
                <div className="stat-label">Grabs</div>
                <div className="stat-sub">
                  {fmtNumber(data.weeks.reduce((n, w) => n + w.imports, 0))} Importe · {fmtNumber(data.weeks.reduce((n, w) => n + w.failed, 0))} fehlgeschlagen
                </div>
              </div>
            </div>
          </div>

          <div className="stats-grid">
            <Card
              title="Verlauf pro Woche"
              actions={
                <div className="seg" role="group" aria-label="Kennzahl">
                  {(Object.keys(METRICS) as (keyof typeof METRICS)[]).map((k) => (
                    <button key={k} className={`seg-btn ${metric === k ? "active" : ""}`} onClick={() => setMetric(k)}>
                      {METRICS[k]}
                    </button>
                  ))}
                </div>
              }
            >
              <WeekColumns weeks={data.weeks} metric={metric} />
            </Card>

            <Card title="Grabs pro Indexer">
              {data.indexers.length === 0 ? (
                <p className="muted">Keine Aktivität im Zeitraum.</p>
              ) : (
                <div className="table-wrap">
                  <table className="table table-compact">
                    <thead>
                      <tr>
                        <th>Indexer</th>
                        <th className="num">Grabs</th>
                        <th className="num">Anfragen</th>
                        <th className="num">Fehler</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.indexers.map((i) => (
                        <tr key={i.name}>
                          <td>{i.name}</td>
                          <td className="num">{fmtNumber(i.grabs)}</td>
                          <td className="num">{fmtNumber(i.queries)}</td>
                          <td className="num">{fmtNumber(i.failed)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Speicher pro Root-Folder">
              {data.root_folders.map((r) => (
                <div key={r.path} className="mb-sm">
                  <div className="row gap-sm">
                    <span className="mono small grow break">{r.path}</span>
                    <span className="small">{fmtSize(r.library_size)} Bibliothek</span>
                  </div>
                  {r.total ? (
                    <>
                      <div className="barlist-track wide" title={`${fmtSize(r.total - (r.free ?? 0))} von ${fmtSize(r.total)} belegt`}>
                        <span className="barlist-fill" style={{ width: `${(100 * (r.total - (r.free ?? 0))) / r.total}%` }} />
                      </div>
                      <div className="muted small">
                        {fmtSize(r.free)} frei von {fmtSize(r.total)}
                      </div>
                    </>
                  ) : (
                    <div className="tone-text-warning small">nicht erreichbar</div>
                  )}
                </div>
              ))}
              {data.root_folders.length === 0 && <p className="muted">Keine Root-Folder.</p>}
            </Card>

            <Card title="Qualitäten">
              <BarList rows={data.qualities} value={(r) => r.size} format={(r) => `${fmtNumber(r.count)} · ${fmtSize(r.size)}`} />
            </Card>
            <Card title="Sprachen">
              <BarList rows={data.languages} value={(r) => r.count} format={(r) => fmtNumber(r.count)} label={(n) => (n === "unbekannt" || n === "Sonstige" ? n : langLabel(n))} />
            </Card>
            <Card title="Video-Codecs">
              <BarList rows={data.codecs} value={(r) => r.count} format={(r) => fmtNumber(r.count)} />
            </Card>
            <Card title="Auflösung (aus Mediainfo)">
              <BarList rows={data.resolutions} value={(r) => r.count} format={(r) => fmtNumber(r.count)} />
            </Card>
            <Card title="Release-Gruppen">
              <BarList rows={data.release_groups} value={(r) => r.count} format={(r) => fmtNumber(r.count)} />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
