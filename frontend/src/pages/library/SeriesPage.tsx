import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Bookmark, BookmarkX, RefreshCw, Tv } from "lucide-react";
import { useSeriesList, useProfiles, useCommand, useStored } from "../../hooks";
import { Empty, ErrorBox, Loading, PageHeader, Progress, Badge } from "../../components/ui";
import { Poster } from "../../components/Media";
import { fmtDate, fmtSize, SERIES_STATUS_LABELS, SERIES_TYPE_LABELS } from "../../format";
import { LibraryToolbar, textMatch, type FilterMode, type SortMode, type ViewMode } from "./common";
import type { Series } from "../../types";

export function seriesProgress(s: Series) {
  const have = s.stats?.monitored_have ?? 0;
  const aired = s.stats?.monitored_aired ?? 0;
  const pct = aired ? (100 * have) / aired : have ? 100 : 0;
  const tone = aired === 0 ? "muted" : have >= aired ? "success" : s.monitored ? (s.status === "ended" ? "danger" : "warning") : "muted";
  return { have, aired, pct, tone };
}

export function SeriesPage() {
  const { data, isLoading, error } = useSeriesList();
  const { data: profiles = [] } = useProfiles();
  const [view, setView] = useStored<ViewMode>("mc-series-view", "grid");
  const [filter, setFilter] = useStored<FilterMode>("mc-series-filter", "all");
  const [sort, setSort] = useStored<SortMode>("mc-series-sort", "title");
  const [search, setSearch] = useState("");
  const command = useCommand();

  const list = useMemo(() => {
    let l = (data ?? []).filter((s) => textMatch(search, s.title, s.original_title, ...(s.alt_titles ?? [])));
    if (filter === "monitored") l = l.filter((s) => s.monitored);
    if (filter === "missing") l = l.filter((s) => (s.stats?.monitored_aired ?? 0) > (s.stats?.monitored_have ?? 0));
    if (filter === "have") l = l.filter((s) => (s.stats?.episode_file_count ?? 0) > 0);
    const r = [...l];
    if (sort === "title") r.sort((a, b) => (a.sort_title || a.title).localeCompare(b.sort_title || b.title, "de"));
    if (sort === "year") r.sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
    if (sort === "added") r.sort((a, b) => (b.added ?? "").localeCompare(a.added ?? ""));
    return r;
  }, [data, search, filter, sort]);

  return (
    <div className="page">
      <PageHeader title="Serien">
        <button className="btn" onClick={() => command("refresh_all")} title="Metadaten aller Filme und Serien aktualisieren">
          <RefreshCw size={15} /> Alle aktualisieren
        </button>
        <Link to="/series/add" className="btn btn-primary">
          <Plus size={16} /> Serie hinzufügen
        </Link>
      </PageHeader>
      <LibraryToolbar view={view} setView={setView} filter={filter} setFilter={setFilter} sort={sort} setSort={setSort} search={search} setSearch={setSearch} count={list.length} />
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && (
        <Empty icon={<Tv size={36} />} title="Noch keine Serien">
          <Link to="/series/add" className="btn btn-primary">
            <Plus size={16} /> Erste Serie hinzufügen
          </Link>
        </Empty>
      )}
      {data && data.length > 0 && list.length === 0 && <Empty title="Keine Treffer für diesen Filter" />}
      {view === "grid" ? (
        <div className="poster-grid">
          {list.map((s) => {
            const p = seriesProgress(s);
            return (
              <Link to={`/series/${s.id}`} key={s.id} className={`poster-card ${s.monitored ? "" : "state-unmonitored"}`} title={s.title}>
                <Poster src={s.images?.poster} title={s.title} kind="series" />
                <div className="poster-card-status">{!s.monitored && <BookmarkX size={14} />}</div>
                <div className="poster-card-info">
                  <div className="poster-card-title">{s.title}</div>
                  <div className="poster-card-sub">
                    {p.have}/{p.aired} · {SERIES_STATUS_LABELS[s.status] ?? s.status}
                  </div>
                  <Progress value={p.pct} tone={p.tone} small title={`${p.have} von ${p.aired} überwachten, ausgestrahlten Episoden vorhanden`} />
                </div>
              </Link>
            );
          })}
        </div>
      ) : (
        list.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-icon" />
                  <th>Titel</th>
                  <th>Jahr</th>
                  <th>Status</th>
                  <th>Sender</th>
                  <th>Typ</th>
                  <th>Profil</th>
                  <th>Nächste Folge</th>
                  <th className="w-progress">Episoden</th>
                  <th className="num">Größe</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => {
                  const p = seriesProgress(s);
                  return (
                    <tr key={s.id}>
                      <td title={s.monitored ? "Überwacht" : "Nicht überwacht"}>{s.monitored ? <Bookmark size={15} className="accent" /> : <BookmarkX size={15} className="muted" />}</td>
                      <td>
                        <Link to={`/series/${s.id}`} className="strong">
                          {s.title}
                        </Link>
                      </td>
                      <td>{s.year ?? "–"}</td>
                      <td>
                        <Badge tone={s.status === "continuing" ? "success" : s.status === "ended" ? "muted" : "info"}>{SERIES_STATUS_LABELS[s.status] ?? s.status}</Badge>
                      </td>
                      <td>{s.network ?? "–"}</td>
                      <td>{SERIES_TYPE_LABELS[s.series_type] ?? s.series_type}</td>
                      <td>{profiles.find((x) => x.id === s.quality_profile_id)?.name ?? "–"}</td>
                      <td>{fmtDate(s.stats?.next_airing)}</td>
                      <td>
                        <div className="progress-labeled">
                          <Progress value={p.pct} tone={p.tone} />
                          <span>
                            {p.have}/{p.aired}
                          </span>
                        </div>
                      </td>
                      <td className="num">{fmtSize(s.stats?.size_on_disk ?? 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
