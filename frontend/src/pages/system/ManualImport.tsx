import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Search, Import, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Card, Empty, Field, Select, Spinner, Badge } from "../../components/ui";
import { FileBrowser } from "../../components/FileBrowser";
import { useToast } from "../../components/Toast";
import { useMovies, useQualities, useSeriesList, useStored } from "../../hooks";
import { epCode, fmtSize, langLabel } from "../../format";
import type { ManualImportItem, ManualImportResult } from "../../types";

interface Row extends ManualImportItem {
  checked: boolean;
  kind: "movie" | "series";
}

export function ManualImportPage() {
  const [path, setPath] = useStored("mc-manual-import-path", "");
  const [browse, setBrowse] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [importing, setImporting] = useState(false);
  const [mode, setMode] = useState<"copy" | "move">("copy");
  const [results, setResults] = useState<ManualImportResult[] | null>(null);
  const { data: movies = [] } = useMovies();
  const { data: series = [] } = useSeriesList();
  const { data: qualities = [] } = useQualities();
  const toast = useToast();
  const qc = useQueryClient();

  const scan = async (p = path) => {
    if (!p) return;
    setScanning(true);
    setResults(null);
    try {
      const res = await api.manualImportScan(p);
      setRows(res.map((r) => ({ ...r, checked: r.rejections.length === 0, kind: r.series_id || r.parsed?.is_tv ? "series" : "movie" })));
    } catch (e) {
      toast.error("Scan fehlgeschlagen", errorMessage(e));
    } finally {
      setScanning(false);
    }
  };

  const upd = (i: number, p: Partial<Row>) => setRows((r) => (r ? r.map((x, k) => (k === i ? { ...x, ...p } : x)) : r));
  const valid = (r: Row) => (r.kind === "movie" ? !!r.movie_id : !!r.series_id && r.episode_ids.length > 0);
  const selected = (rows ?? []).filter((r) => r.checked && valid(r));

  const run = async () => {
    setImporting(true);
    try {
      const res = await api.manualImport(
        selected.map((r) => ({
          path: r.path,
          movie_id: r.kind === "movie" ? r.movie_id : null,
          series_id: r.kind === "series" ? r.series_id : null,
          episode_ids: r.kind === "series" ? r.episode_ids : [],
          quality: r.quality,
          languages: r.languages,
        })),
        mode,
      );
      setResults(res);
      const ok = res.filter((r) => r.ok).length;
      if (ok === res.length) toast.success(`${ok} Datei(en) importiert`);
      else toast.warning(`${ok} von ${res.length} importiert`, res.filter((r) => !r.ok).map((r) => r.error).join("\n"));
      qc.invalidateQueries({ queryKey: ["movies"] });
      qc.invalidateQueries({ queryKey: ["series"] });
      qc.invalidateQueries({ queryKey: ["episodes"] });
      setRows((rs) => (rs ? rs.filter((r) => !res.find((x) => x.path === r.path && x.ok)) : rs));
    } catch (e) {
      toast.error("Import fehlgeschlagen", errorMessage(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="settings-page">
      <Card title="Manueller Import">
        <p className="muted">Importiert beliebige Videodateien (z. B. aus einem Download-Ordner) in die Bibliothek. Zuordnung, Qualität und Sprachen lassen sich vor dem Import korrigieren.</p>
        <Field label="Ordner oder Datei">
          <form
            className="row gap-sm"
            onSubmit={(e) => {
              e.preventDefault();
              scan();
            }}
          >
            <input className="input mono grow" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/data/downloads/complete" aria-label="Pfad" />
            <button type="button" className="icon-btn" onClick={() => setBrowse(true)} title="Durchsuchen" aria-label="Durchsuchen">
              <FolderOpen size={17} />
            </button>
            <button className="btn btn-primary" type="submit" disabled={!path || scanning}>
              {scanning ? <Spinner size={14} /> : <Search size={15} />} Scannen
            </button>
          </form>
        </Field>
      </Card>

      {rows && (
        <Card
          title={`${rows.length} Datei(en)`}
          actions={
            <>
              <Select
                value={mode}
                onValue={setMode}
                aria-label="Importmodus"
                options={[
                  { value: "copy", label: "Kopieren / Hardlink" },
                  { value: "move", label: "Verschieben" },
                ]}
              />
              <button className="btn btn-primary" onClick={run} disabled={importing || selected.length === 0}>
                {importing ? <Spinner size={14} /> : <Import size={15} />} {selected.length} importieren
              </button>
            </>
          }
        >
          {rows.length === 0 ? (
            <Empty title="Keine Videodateien gefunden" />
          ) : (
            <div className="table-wrap">
              <table className="table table-compact manual-import">
                <thead>
                  <tr>
                    <th className="w-icon">
                      <input type="checkbox" aria-label="Alle auswählen" checked={rows.every((r) => r.checked)} onChange={(e) => setRows(rows.map((r) => ({ ...r, checked: e.target.checked })))} />
                    </th>
                    <th>Datei</th>
                    <th>Typ</th>
                    <th>Zuordnung</th>
                    <th>Qualität</th>
                    <th>Sprachen</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.path} className={!valid(r) ? "row-warn" : ""}>
                      <td>
                        <input type="checkbox" checked={r.checked} onChange={(e) => upd(i, { checked: e.target.checked })} aria-label="Auswählen" />
                      </td>
                      <td className="break small">
                        <div className="mono">{r.path.split(/[\\/]/).pop()}</div>
                        <div className="muted">{fmtSize(r.size)}</div>
                        {r.rejections.map((x, k) => (
                          <div key={k} className="tone-text-warning">
                            <AlertTriangle size={12} /> {x}
                          </div>
                        ))}
                      </td>
                      <td>
                        <Select
                          value={r.kind}
                          onValue={(v) => upd(i, { kind: v })}
                          options={[
                            { value: "movie", label: "Film" },
                            { value: "series", label: "Serie" },
                          ]}
                          aria-label="Typ"
                        />
                      </td>
                      <td className="mi-target">
                        {r.kind === "movie" ? (
                          <Select
                            value={r.movie_id ?? 0}
                            onValue={(v) => upd(i, { movie_id: v || null })}
                            options={[{ value: 0, label: "– Film wählen –" }, ...movies.map((m) => ({ value: m.id, label: `${m.title}${m.year ? ` (${m.year})` : ""}` }))]}
                            aria-label="Film"
                          />
                        ) : (
                          <div className="col gap-xs">
                            <Select
                              value={r.series_id ?? 0}
                              onValue={(v) => upd(i, { series_id: v || null, episode_ids: [] })}
                              options={[{ value: 0, label: "– Serie wählen –" }, ...series.map((s) => ({ value: s.id, label: s.title }))]}
                              aria-label="Serie"
                            />
                            {r.series_id ? <EpisodePicker seriesId={r.series_id} value={r.episode_ids} onChange={(v) => upd(i, { episode_ids: v })} /> : null}
                          </div>
                        )}
                      </td>
                      <td>
                        <Select value={r.quality} onValue={(v) => upd(i, { quality: v })} options={qualities.map((q) => ({ value: q.name, label: q.name }))} aria-label="Qualität" />
                      </td>
                      <td className="small">{r.languages.map(langLabel).join(", ") || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {results && (
        <Card title="Ergebnis">
          <ul className="result-list">
            {results.map((r) => (
              <li key={r.path}>
                {r.ok ? <CheckCircle2 size={15} className="tone-text-success" /> : <XCircle size={15} className="tone-text-danger" />} <span className="mono small break">{r.path}</span>
                {r.error && <Badge tone="danger">{r.error}</Badge>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {browse && (
        <FileBrowser
          title="Ordner oder Datei wählen"
          initial={path}
          includeFiles
          onClose={() => setBrowse(false)}
          onSelect={(p) => {
            setPath(p);
            setBrowse(false);
            scan(p);
          }}
        />
      )}
    </div>
  );
}

function EpisodePicker({ seriesId, value, onChange }: { seriesId: number; value: number[]; onChange: (v: number[]) => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["episodes", seriesId], queryFn: () => api.episodes(seriesId) });
  if (isLoading) return <Spinner size={14} />;
  return (
    <select
      multiple
      className="input select-multi"
      value={value.map(String)}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
      aria-label="Episoden (Strg/Cmd für Mehrfachauswahl)"
      title="Strg/Cmd gedrückt halten für Mehrfachauswahl"
    >
      {(data ?? []).map((e) => (
        <option key={e.id} value={e.id}>
          {epCode(e.season, e.number)} {e.title ?? ""}
          {e.has_file ? " ✓" : ""}
        </option>
      ))}
    </select>
  );
}
