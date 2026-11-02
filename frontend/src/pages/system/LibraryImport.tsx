import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Plus, CheckCircle2, FolderSearch, Wand2 } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Select, Spinner, Toggle } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useProfiles, useRootFolders } from "../../hooks";
import { MONITOR_OPTIONS } from "../../format";
import { SourceBadges, Poster } from "../../components/Media";
import { lookupSources } from "../library/AddMovie";
import type { LookupResult, RootFolder, UnmappedFolder } from "../../types";

interface RowState {
  results?: LookupResult[];
  loading?: boolean;
  error?: string;
  sel: number;
  done?: { id: number; kind: "movie" | "series" };
  adding?: boolean;
  checked: boolean;
}

export function LibraryImportPage() {
  const { data: roots = [], isLoading } = useRootFolders();
  const [rootId, setRootId] = useState(0);
  useEffect(() => {
    if (!rootId && roots.length) setRootId(roots[0].id);
  }, [roots, rootId]);
  const root = roots.find((r) => r.id === rootId);

  return (
    <div className="settings-page">
      <Card title="Bibliotheksimport">
        <p className="muted">Durchsucht einen Root-Folder nach Ordnern, die noch keinem Film bzw. keiner Serie zugeordnet sind, und schlägt passende Einträge vor. Ordnernamen wie „Titel (2020) [tmdbid-123]“ werden direkt erkannt.</p>
        {isLoading && <Loading />}
        {!isLoading && roots.length === 0 && (
          <Empty icon={<FolderSearch size={32} />} title="Kein Root-Folder">
            <Link to="/settings/media">Root-Folder anlegen</Link>
          </Empty>
        )}
        {roots.length > 0 && (
          <Field label="Root-Folder">
            <Select value={rootId} onValue={setRootId} options={roots.map((r) => ({ value: r.id, label: `${r.path} (${r.media_type === "movie" ? "Filme" : r.media_type === "anime" ? "Anime" : "Serien"})` }))} />
          </Field>
        )}
      </Card>
      {root && <ImportList key={root.id} root={root} />}
    </div>
  );
}

function ImportList({ root }: { root: RootFolder }) {
  const { data, isLoading, error, refetch, isFetching } = useQuery({ queryKey: ["libraryimport", root.id], queryFn: () => api.libraryImport(root.id) });
  const { data: profiles = [] } = useProfiles();
  const [profile, setProfile] = useState(0);
  const [monitor, setMonitor] = useState("all");
  const [search, setSearch] = useState(false);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [bulk, setBulk] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  const isMovie = root.media_type === "movie";

  useEffect(() => {
    if (!profile && profiles.length) setProfile(profiles[0].id);
  }, [profiles, profile]);

  const row = (f: UnmappedFolder): RowState => rows[f.path] ?? { sel: 0, checked: true };
  const patch = (path: string, p: Partial<RowState>) => setRows((r) => ({ ...r, [path]: { ...(r[path] ?? { sel: 0, checked: true }), ...p } }));

  const lookup = async (f: UnmappedFolder) => {
    patch(f.path, { loading: true, error: undefined });
    try {
      const res = await api.libraryImportLookup({ title: f.title, year: f.year, ids: f.ids, media_type: f.media_type });
      patch(f.path, { results: res, loading: false, sel: 0 });
      return res;
    } catch (e) {
      patch(f.path, { loading: false, error: errorMessage(e) });
      return [];
    }
  };

  const add = async (f: UnmappedFolder, results?: LookupResult[]) => {
    const st = row(f);
    const r = (results ?? st.results)?.[st.sel];
    if (!r) return false;
    if (r.existing_id) {
      patch(f.path, { done: { id: r.existing_id, kind: isMovie ? "movie" : "series" } });
      return true;
    }
    patch(f.path, { adding: true });
    try {
      let id: number;
      if (isMovie) {
        const m = await api.addMovie({ ids: r.ids, quality_profile_id: profile, root_folder: root.path, monitored: true, minimum_availability: "released", tags: [], search, path: f.path });
        id = m.id;
      } else {
        const s = await api.addSeries({ ids: r.ids, quality_profile_id: profile, root_folder: root.path, monitored: monitor !== "none", monitor, series_type: root.media_type === "anime" || r.is_anime ? "anime" : "standard", season_folder: true, tags: [], episode_source: "", search, path: f.path });
        id = s.id;
      }
      patch(f.path, { adding: false, done: { id, kind: isMovie ? "movie" : "series" } });
      return true;
    } catch (e) {
      patch(f.path, { adding: false, error: errorMessage(e) });
      return false;
    }
  };

  const lookupAll = async () => {
    setBulk(true);
    for (const f of data ?? []) {
      if (!row(f).results && !row(f).done) await lookup(f);
    }
    setBulk(false);
  };

  const importChecked = async () => {
    setBulk(true);
    let n = 0;
    for (const f of data ?? []) {
      const st = row(f);
      if (!st.checked || st.done || !st.results?.length) continue;
      if (await add(f)) n++;
    }
    setBulk(false);
    toast.success(`${n} Einträge importiert`);
    qc.invalidateQueries({ queryKey: [isMovie ? "movies" : "series"] });
  };

  if (isLoading) return <Loading label="Scanne Ordner…" />;
  if (error) return <ErrorBox error={error} />;
  const list = data ?? [];
  const ready = list.filter((f) => row(f).checked && !row(f).done && row(f).results?.length).length;

  return (
    <Card
      title={`${list.length} nicht zugeordnete Ordner`}
      actions={
        <button className="btn btn-sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? <Spinner size={14} /> : <Search size={14} />} Neu scannen
        </button>
      }
    >
      {list.length === 0 ? (
        <div className="health-ok">
          <CheckCircle2 size={18} /> Alle Ordner sind zugeordnet.
        </div>
      ) : (
        <>
          <div className="toolbar">
            <Select value={profile} onValue={setProfile} options={profiles.map((p) => ({ value: p.id, label: `Profil: ${p.name}` }))} aria-label="Qualitätsprofil" />
            {!isMovie && <Select value={monitor} onValue={setMonitor} options={MONITOR_OPTIONS.map((o) => ({ ...o, label: `Überwachen: ${o.label}` }))} aria-label="Überwachen" />}
            <Toggle checked={search} onChange={setSearch} label="Nach Import suchen" />
            <button className="btn" onClick={lookupAll} disabled={bulk}>
              {bulk ? <Spinner size={14} /> : <Wand2 size={15} />} Alle zuordnen
            </button>
            <button className="btn btn-primary" onClick={importChecked} disabled={bulk || !ready}>
              <Plus size={15} /> {ready} importieren
            </button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-icon" />
                  <th>Ordner</th>
                  <th>Zuordnung</th>
                  <th className="w-actions" />
                </tr>
              </thead>
              <tbody>
                {list.map((f) => {
                  const st = row(f);
                  const sel = st.results?.[st.sel];
                  return (
                    <tr key={f.path}>
                      <td>
                        <input type="checkbox" checked={st.checked} disabled={!!st.done} onChange={(e) => patch(f.path, { checked: e.target.checked })} aria-label="Auswählen" />
                      </td>
                      <td>
                        <div className="strong">{f.folder}</div>
                        <div className="muted small">
                          erkannt: {f.title} {f.year ? `(${f.year})` : ""} {Object.entries(f.ids ?? {}).map(([k, v]) => <Badge key={k} tone="accent">{k}:{String(v)}</Badge>)}
                        </div>
                      </td>
                      <td>
                        {st.loading && <Spinner size={14} label="Suche…" />}
                        {st.error && <span className="tone-text-danger small">{st.error}</span>}
                        {st.results && st.results.length === 0 && <span className="muted">Kein Treffer</span>}
                        {st.results && st.results.length > 0 && (
                          <div className="match">
                            {sel && <Poster src={sel.images?.poster} title={sel.title} kind={isMovie ? "movie" : "series"} className="poster-xs" />}
                            <div className="grow">
                              <Select
                                value={st.sel}
                                onValue={(v) => patch(f.path, { sel: v })}
                                disabled={!!st.done}
                                options={st.results.map((r, i) => ({ value: i, label: `${r.title}${r.year ? ` (${r.year})` : ""}${r.existing_id ? " – bereits vorhanden" : ""}` }))}
                              />
                              {sel && <SourceBadges sources={lookupSources(sel)} />}
                            </div>
                          </div>
                        )}
                      </td>
                      <td className="actions">
                        {st.done ? (
                          <Link to={st.done.kind === "movie" ? `/movies/${st.done.id}` : `/series/${st.done.id}`} className="btn btn-sm">
                            <CheckCircle2 size={14} className="tone-text-success" /> Öffnen
                          </Link>
                        ) : !st.results ? (
                          <button className="btn btn-sm" onClick={() => lookup(f)} disabled={st.loading}>
                            <Search size={14} /> Suchen
                          </button>
                        ) : (
                          <button className="btn btn-sm btn-primary" onClick={() => add(f)} disabled={st.adding || !sel || !profile}>
                            {st.adding ? <Spinner size={14} /> : <Plus size={14} />} Hinzufügen
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}
