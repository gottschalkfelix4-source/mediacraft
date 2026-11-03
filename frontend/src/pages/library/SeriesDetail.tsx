import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search, UserSearch, RefreshCw, FileEdit, Link2, Pencil, Trash2, Bookmark, BookmarkX, FolderOpen, Clock, ExternalLink, ChevronDown, ChevronRight, ListChecks, FileX, Tv,
} from "lucide-react";
import { api, errorMessage } from "../../api";
import { useApiMutation, useCommand, useNow, useProfiles, useTags } from "../../hooks";
import { Badge, Card, ErrorBox, Field, Loading, Select, Tabs, TextInput, Toggle, Spinner, Progress } from "../../components/ui";
import { Fanart, Poster, Ratings, SourceBadges, TagList } from "../../components/Media";
import { Modal, useConfirm } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { InteractiveSearch } from "../../components/InteractiveSearch";
import { DownloadStatus, useDownloads } from "../../components/DownloadStatus";
import { useToast } from "../../components/Toast";
import { epCode, fmtDate, fmtDateTime, fmtSize, langLabel, parseDate, providerLabel, MONITOR_OPTIONS, SERIES_STATUS_LABELS, SERIES_TYPE_LABELS } from "../../format";
import { HistoryTable } from "./HistoryTable";
import { RenameDialog } from "./RenameDialog";
import { DeleteDialog } from "./DeleteDialog";
import { RematchDialog } from "./RematchDialog";
import { EPISODE_SOURCE_OPTIONS, SERIES_TYPE_OPTIONS } from "./AddSeries";
import { seriesProgress } from "./SeriesPage";
import type { Episode, Series, SeriesType } from "../../types";

type SearchTarget = { title: string; key: unknown[]; opts: { season?: number; episode_id?: number } };

export function SeriesDetail() {
  const id = Number(useParams().id);
  const { data: s, isLoading, error } = useQuery({ queryKey: ["series", id], queryFn: () => api.series(id) });
  const eps = useQuery({ queryKey: ["episodes", id], queryFn: () => api.episodes(id) });
  const { data: profiles = [] } = useProfiles();
  const { data: tags = [] } = useTags();
  const [tab, setTab] = useState<"seasons" | "history">("seasons");
  const [dialog, setDialog] = useState<null | "edit" | "delete" | "rename" | "monitor" | "rematch">(null);
  const [searchTarget, setSearchTarget] = useState<SearchTarget | null>(null);
  const [expanded, setExpanded] = useState<Set<number> | null>(null);
  const command = useCommand();
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();

  const toggleMonitor = useApiMutation((v: boolean) => api.updateSeries(id, { monitored: v }), {
    invalidate: [["series"]],
    success: (_r, v) => (v ? "Serie wird überwacht" : "Überwachung beendet"),
  });

  const bySeason = useMemo(() => {
    const m = new Map<number, Episode[]>();
    for (const e of eps.data ?? []) {
      if (!m.has(e.season)) m.set(e.season, []);
      m.get(e.season)!.push(e);
    }
    for (const l of m.values()) l.sort((a, b) => b.number - a.number);
    return m;
  }, [eps.data]);

  if (isLoading) return <Loading />;
  if (error || !s) return <ErrorBox error={error} />;

  const seasons = [...(s.seasons ?? [])].sort((a, b) => (a.number === 0 ? 1 : b.number === 0 ? -1 : b.number - a.number));
  // expand the latest regular season by default
  const exp = expanded ?? new Set(seasons.filter((x) => x.number > 0).slice(0, 1).map((x) => x.number));
  const toggleExp = (n: number) => {
    const next = new Set(exp);
    if (next.has(n)) next.delete(n);
    else next.add(n);
    setExpanded(next);
  };
  const profile = profiles.find((p) => p.id === s.quality_profile_id);
  const prog = seriesProgress(s);

  return (
    <div className="page page-detail">
      <Fanart src={s.images?.fanart}>
        <Poster src={s.images?.poster} title={s.title} kind="series" className="poster-lg" />
        <div className="detail-info">
          <div className="detail-title-row">
            <button className={`icon-btn monitor-btn ${s.monitored ? "on" : ""}`} title={s.monitored ? "Überwacht – klicken zum Beenden" : "Nicht überwacht – klicken zum Überwachen"} aria-label="Überwachung umschalten" onClick={() => toggleMonitor.mutate(!s.monitored)}>
              {s.monitored ? <Bookmark size={22} /> : <BookmarkX size={22} />}
            </button>
            <h1>
              {s.title} {s.year ? <span className="muted">({s.year})</span> : null}
            </h1>
          </div>
          {s.original_title && s.original_title !== s.title && <div className="muted">{s.original_title}</div>}
          <div className="detail-meta">
            {s.runtime ? <span><Clock size={14} /> {s.runtime} min</span> : null}
            {s.network && <span><Tv size={14} /> {s.network}</span>}
            {s.air_time && <span>{s.air_time} Uhr (Sendezeit)</span>}
            {s.certification && <Badge tone="muted">{s.certification}</Badge>}
            <Badge tone={s.status === "continuing" ? "success" : "muted"}>{SERIES_STATUS_LABELS[s.status] ?? s.status}</Badge>
            <Badge tone="info">{SERIES_TYPE_LABELS[s.series_type] ?? s.series_type}</Badge>
            <span>{fmtSize(s.stats?.size_on_disk ?? 0)}</span>
          </div>
          {s.genres?.length > 0 && <div className="genres">{s.genres.map((g) => <span key={g} className="genre">{g}</span>)}</div>}
          <Ratings ratings={s.ratings} />
          <p className="detail-overview">{s.overview || <span className="muted">Keine Beschreibung.</span>}</p>
          <div className="detail-progress">
            <Progress value={prog.pct} tone={prog.tone} />
            <span>{prog.have}/{prog.aired} Episoden{s.stats?.next_airing ? ` · nächste: ${fmtDateTime(s.stats.next_airing)}` : ""}</span>
          </div>
          <div className="detail-facts">
            <span><FolderOpen size={14} /> <span className="mono">{s.path}</span></span>
            <span>Profil: <strong>{profile?.name ?? "–"}</strong></span>
            <span>Episodenquelle: <strong>{s.episode_source ? providerLabel(s.episode_source) : "automatisch"}</strong></span>
            <TagList ids={s.tags} tags={tags} />
          </div>
          <div className="detail-sources">
            <span className="muted small">Metadaten:</span> <SourceBadges sources={s.metadata_sources} />
            {s.tvdb_id && <a className="ext" href={`https://thetvdb.com/dereferrer/series/${s.tvdb_id}`} target="_blank" rel="noreferrer noopener">TVDB <ExternalLink size={11} /></a>}
            {s.tmdb_id && <a className="ext" href={`https://www.themoviedb.org/tv/${s.tmdb_id}`} target="_blank" rel="noreferrer noopener">TMDB <ExternalLink size={11} /></a>}
            {s.tvmaze_id && <a className="ext" href={`https://www.tvmaze.com/shows/${s.tvmaze_id}`} target="_blank" rel="noreferrer noopener">TVmaze <ExternalLink size={11} /></a>}
            {s.imdb_id && <a className="ext" href={`https://www.imdb.com/title/${s.imdb_id}/`} target="_blank" rel="noreferrer noopener">IMDb <ExternalLink size={11} /></a>}
            {s.anilist_id && <a className="ext" href={`https://anilist.co/anime/${s.anilist_id}`} target="_blank" rel="noreferrer noopener">AniList <ExternalLink size={11} /></a>}
          </div>
        </div>
      </Fanart>

      <div className="action-bar">
        <button className="btn btn-primary" onClick={() => command("series_search", { series_id: s.id }, `Suche „${s.title}“`)} title="Alle fehlenden/unter Cutoff liegenden Episoden suchen">
          <Search size={16} /> Fehlende suchen
        </button>
        <button className="btn" onClick={() => command("refresh_series", { series_id: s.id }, `Aktualisierung „${s.title}“`)} title="Metadaten aktualisieren und Ordner scannen">
          <RefreshCw size={16} /> Aktualisieren
        </button>
        <button className="btn" onClick={() => setDialog("rematch")} title="Falsch erkannt? Mit einem anderen Metadaten-Eintrag verknüpfen">
          <Link2 size={16} /> Neu zuordnen
        </button>
        <button className="btn" onClick={() => setDialog("rename")} title="Dateien umbenennen">
          <FileEdit size={16} /> Umbenennen
        </button>
        <button className="btn" onClick={() => setDialog("monitor")} title="Überwachung für Episoden neu setzen">
          <ListChecks size={16} /> Überwachung
        </button>
        <button className="btn" onClick={() => setDialog("edit")} title="Bearbeiten">
          <Pencil size={16} /> Bearbeiten
        </button>
        <button className="btn btn-danger-outline" onClick={() => setDialog("delete")} title="Löschen">
          <Trash2 size={16} /> Löschen
        </button>
      </div>

      <Tabs
        tabs={[
          { key: "seasons", label: "Staffeln", count: seasons.length },
          { key: "history", label: "Verlauf" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "seasons" ? (
        <div className="seasons">
          {eps.isLoading && <Loading label="Lade Episoden…" />}
          {eps.error ? <ErrorBox error={eps.error} /> : null}
          {seasons.length === 0 && !eps.isLoading && <div className="muted">Keine Staffeln bekannt – Serie aktualisieren?</div>}
          {seasons.map((se) => (
            <SeasonBlock
              key={se.number}
              series={s}
              season={se.number}
              monitored={se.monitored}
              stats={se.stats}
              episodes={bySeason.get(se.number) ?? []}
              open={exp.has(se.number)}
              onToggle={() => toggleExp(se.number)}
              onInteractive={(t) => setSearchTarget(t)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <SeriesHistory id={s.id} />
        </Card>
      )}

      {dialog === "rematch" && <RematchDialog kind="series" item={s} onClose={() => setDialog(null)} />}
      {dialog === "edit" && <EditSeriesDialog s={s} onClose={() => setDialog(null)} />}
      {dialog === "monitor" && <MonitorDialog s={s} onClose={() => setDialog(null)} />}
      {dialog === "delete" && (
        <DeleteDialog
          title={`„${s.title}“ löschen`}
          path={s.path}
          onClose={() => setDialog(null)}
          onConfirm={async (files, exclude) => {
            await api.deleteSeries(s.id, files, exclude);
            toast.success("Serie gelöscht", s.title);
            qc.removeQueries({ queryKey: ["series", id] });
            qc.invalidateQueries({ queryKey: ["series"] });
            nav("/series");
          }}
        />
      )}
      {dialog === "rename" && <RenameDialog load={() => api.seriesRename(s.id)} queryKey={["rename", "series", s.id]} onApply={() => command("rename_series", { series_id: s.id }, "Umbenennen")} onClose={() => setDialog(null)} />}
      {searchTarget && <InteractiveSearch title={searchTarget.title} queryKey={searchTarget.key} fetcher={() => api.seriesReleases(s.id, searchTarget.opts)} onClose={() => setSearchTarget(null)} />}
    </div>
  );
}

function SeasonBlock({ series, season, monitored, stats, episodes, open, onToggle, onInteractive }: {
  series: Series;
  season: number;
  monitored: boolean;
  stats: { total: number; files: number; aired: number; monitored: number };
  episodes: Episode[];
  open: boolean;
  onToggle: () => void;
  onInteractive: (t: SearchTarget) => void;
}) {
  const command = useCommand();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const now = useNow(60_000);
  const downloads = useDownloads();
  const label = season === 0 ? "Specials" : `Staffel ${season}`;

  const setSeasonMon = useApiMutation((v: boolean) => api.updateSeason(series.id, season, v), {
    invalidate: [["series", series.id], ["episodes", series.id], ["series"]],
  });
  const setEpMon = async (e: Episode, v: boolean) => {
    // optimistic update
    qc.setQueryData<Episode[]>(["episodes", series.id], (old) => old?.map((x) => (x.id === e.id ? { ...x, monitored: v } : x)));
    try {
      await api.monitorEpisodes([e.id], v);
      qc.invalidateQueries({ queryKey: ["series", series.id] });
    } catch (err) {
      toast.error("Ändern fehlgeschlagen", errorMessage(err));
      qc.invalidateQueries({ queryKey: ["episodes", series.id] });
    }
  };
  const deleteFile = async (e: Episode) => {
    if (!e.file) return;
    const ok = await confirm({ title: "Episodendatei löschen?", message: <code className="break">{e.file.path}</code>, confirmLabel: "Löschen", danger: true });
    if (!ok) return;
    try {
      await api.deleteEpisodeFile(e.file.id);
      toast.success("Datei gelöscht");
      qc.invalidateQueries({ queryKey: ["episodes", series.id] });
      qc.invalidateQueries({ queryKey: ["series"] });
    } catch (err) {
      toast.error("Löschen fehlgeschlagen", errorMessage(err));
    }
  };

  const airedTotal = stats.aired;
  const pct = airedTotal ? (100 * Math.min(stats.files, airedTotal)) / airedTotal : stats.files ? 100 : 0;
  const tone = stats.files >= airedTotal && airedTotal > 0 ? "success" : monitored ? "warning" : "muted";

  return (
    <section className={`season ${open ? "open" : ""}`}>
      <div className="season-head">
        <button className={`icon-btn monitor-btn ${monitored ? "on" : ""}`} title={monitored ? "Staffel überwacht" : "Staffel nicht überwacht"} aria-label={`${label} Überwachung umschalten`} onClick={() => setSeasonMon.mutate(!monitored)}>
          {monitored ? <Bookmark size={18} /> : <BookmarkX size={18} />}
        </button>
        <button className="season-title" onClick={onToggle} aria-expanded={open}>
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <h3>{label}</h3>
          <span className="muted small">
            {stats.files}/{stats.total} Dateien · {stats.aired} ausgestrahlt
          </span>
        </button>
        <div className="season-progress">
          <Progress value={pct} tone={tone} small />
        </div>
        <div className="season-actions">
          <button className="icon-btn" title={`${label}: automatisch suchen`} aria-label="Staffel automatisch suchen" onClick={() => command("season_search", { series_id: series.id, season }, `Suche ${series.title} ${label}`)}>
            <Search size={16} />
          </button>
          <button className="icon-btn" title={`${label}: interaktive Suche`} aria-label="Staffel interaktiv suchen" onClick={() => onInteractive({ title: `Interaktive Suche: ${series.title} – ${label}`, key: ["series", series.id, "season", season], opts: { season } })}>
            <UserSearch size={16} />
          </button>
        </div>
      </div>
      {open && (
        <div className="table-wrap">
          <table className="table table-compact episodes">
            <thead>
              <tr>
                <th className="w-icon" />
                <th className="w-num">#</th>
                <th>Titel</th>
                <th>Ausstrahlung</th>
                <th>Datei</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {episodes.map((e) => {
                const air = parseDate(e.air_date_utc);
                const aired = air ? air.getTime() <= now.getTime() : false;
                const state = e.has_file ? "has-file" : !aired ? "upcoming" : e.monitored ? "missing" : "unmonitored";
                return (
                  <tr key={e.id} className={`ep-${state}`}>
                    <td>
                      <button className={`icon-btn monitor-btn small ${e.monitored ? "on" : ""}`} title={e.monitored ? "Überwacht" : "Nicht überwacht"} aria-label="Episode überwachen umschalten" onClick={() => setEpMon(e, !e.monitored)}>
                        {e.monitored ? <Bookmark size={15} /> : <BookmarkX size={15} />}
                      </button>
                    </td>
                    <td className="nowrap">
                      {e.number}
                      {e.absolute_number != null && series.series_type === "anime" && <span className="muted small"> ({e.absolute_number})</span>}
                    </td>
                    <td>
                      <span title={e.overview ?? undefined}>{e.title || <span className="muted">TBA</span>}</span>
                    </td>
                    <td className="nowrap" title={air ? fmtDateTime(air) : undefined}>
                      {air ? fmtDate(air) : e.air_date ? fmtDate(e.air_date) : "TBA"}
                    </td>
                    <td>
                      {downloads.episodes.get(e.id) ? (
                        <DownloadStatus q={downloads.episodes.get(e.id)!} />
                      ) : e.file ? (
                        <span className="file-cell" title={`${e.file.path}\n${fmtSize(e.file.size)}${e.file.languages?.length ? " · " + e.file.languages.map(langLabel).join(", ") : ""}`}>
                          <Badge tone="success">{e.file.quality}</Badge>
                          <span className="muted small">{fmtSize(e.file.size)}</span>
                        </span>
                      ) : e.has_file ? (
                        <Badge tone="success">vorhanden</Badge>
                      ) : aired ? (
                        <Badge tone={e.monitored ? "danger" : "muted"}>fehlt</Badge>
                      ) : (
                        <Badge tone="info">demnächst</Badge>
                      )}
                    </td>
                    <td className="actions">
                      <button className="icon-btn" title="Automatisch suchen" aria-label="Episode automatisch suchen" onClick={() => command("episode_search", { series_id: series.id, episode_ids: [e.id] }, `Suche ${epCode(e.season, e.number)}`)}>
                        <Search size={15} />
                      </button>
                      <button className="icon-btn" title="Interaktive Suche" aria-label="Episode interaktiv suchen" onClick={() => onInteractive({ title: `Interaktive Suche: ${series.title} ${epCode(e.season, e.number)}`, key: ["series", series.id, "episode", e.id], opts: { episode_id: e.id } })}>
                        <UserSearch size={15} />
                      </button>
                      {e.file && (
                        <button className="icon-btn danger" title="Datei löschen" aria-label="Episodendatei löschen" onClick={() => deleteFile(e)}>
                          <FileX size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {episodes.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    Keine Episoden
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SeriesHistory({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["history", "series", id], queryFn: () => api.seriesHistory(id) });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  return <HistoryTable records={data ?? []} />;
}

function EditSeriesDialog({ s, onClose }: { s: Series; onClose: () => void }) {
  const { data: profiles = [] } = useProfiles();
  const [profile, setProfile] = useState(s.quality_profile_id);
  const [type, setType] = useState<SeriesType>(s.series_type);
  const [source, setSource] = useState(s.episode_source ?? "");
  const [monitored, setMonitored] = useState(s.monitored);
  const [newSeasons, setNewSeasons] = useState(s.monitor_new_seasons);
  const [seasonFolder, setSeasonFolder] = useState(s.season_folder);
  const [tags, setTags] = useState(s.tags ?? []);
  const [path, setPath] = useState(s.path);
  const save = useApiMutation(
    () => api.updateSeries(s.id, { quality_profile_id: profile, series_type: type, episode_source: source, monitored, monitor_new_seasons: newSeasons, season_folder: seasonFolder, tags, path }),
    { invalidate: [["series"]], success: "Gespeichert", onSuccess: onClose },
  );
  return (
    <Modal
      title={`Bearbeiten: ${s.title}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={() => save.mutate(undefined)} disabled={save.isPending}>
            {save.isPending && <Spinner size={14} />} Speichern
          </button>
        </>
      }
    >
      <Field label="Qualitätsprofil">
        <Select value={profile} onValue={setProfile} options={profiles.map((p) => ({ value: p.id, label: p.name }))} />
      </Field>
      <Field label="Serientyp">
        <Select<SeriesType> value={type} onValue={setType} options={SERIES_TYPE_OPTIONS} />
      </Field>
      <Field label="Episodenquelle" help="Änderung wirkt beim nächsten Aktualisieren – die Episodenliste wird dann neu aufgebaut.">
        <Select value={source} onValue={setSource} options={EPISODE_SOURCE_OPTIONS} />
      </Field>
      <Field label="Pfad" help="Ändert nur den gespeicherten Pfad, Dateien werden nicht verschoben.">
        <TextInput value={path} onValue={setPath} className="mono" />
      </Field>
      <Field label="Tags">
        <TagSelect value={tags} onChange={setTags} />
      </Field>
      <div className="col gap-sm">
        <Toggle checked={monitored} onChange={setMonitored} label="Serie überwacht" />
        <Toggle checked={newSeasons} onChange={setNewSeasons} label="Neue Staffeln automatisch überwachen" />
        <Toggle checked={seasonFolder} onChange={setSeasonFolder} label="Staffelordner verwenden" />
      </div>
    </Modal>
  );
}

function MonitorDialog({ s, onClose }: { s: Series; onClose: () => void }) {
  const [opt, setOpt] = useState("missing");
  const save = useApiMutation(() => api.seriesMonitoring(s.id, opt), {
    invalidate: [["series"], ["episodes", s.id]],
    success: "Überwachung aktualisiert",
    onSuccess: onClose,
  });
  return (
    <Modal
      title="Episoden-Überwachung"
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={() => save.mutate(undefined)} disabled={save.isPending}>Übernehmen</button>
        </>
      }
    >
      <p className="muted">Setzt die Überwachung aller Episoden von „{s.title}“ neu.</p>
      <Field label="Überwachen">
        <Select value={opt} onValue={setOpt} options={MONITOR_OPTIONS} />
      </Field>
    </Modal>
  );
}
