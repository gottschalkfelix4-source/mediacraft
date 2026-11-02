import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Bookmark, BookmarkX, CheckCircle2, CircleDashed, RefreshCw, Film } from "lucide-react";
import { useMovies, useProfiles, useCommand, useStored } from "../../hooks";
import { Empty, ErrorBox, Loading, PageHeader, Badge } from "../../components/ui";
import { Poster } from "../../components/Media";
import { fmtDate, fmtSize, AVAILABILITY_LABELS, MOVIE_STATUS_LABELS } from "../../format";
import { LibraryToolbar, textMatch, type FilterMode, type SortMode, type ViewMode } from "./common";
import type { Movie } from "../../types";

export function MoviesPage() {
  const { data, isLoading, error } = useMovies();
  const { data: profiles = [] } = useProfiles();
  const [view, setView] = useStored<ViewMode>("mc-movies-view", "grid");
  const [filter, setFilter] = useStored<FilterMode>("mc-movies-filter", "all");
  const [sort, setSort] = useStored<SortMode>("mc-movies-sort", "title");
  const [search, setSearch] = useState("");
  const command = useCommand();

  const list = useMemo(() => {
    let l = (data ?? []).filter((m) => textMatch(search, m.title, m.original_title, ...(m.alt_titles ?? [])));
    if (filter === "monitored") l = l.filter((m) => m.monitored);
    if (filter === "missing") l = l.filter((m) => m.monitored && !m.has_file);
    if (filter === "have") l = l.filter((m) => m.has_file);
    const s = [...l];
    if (sort === "title") s.sort((a, b) => (a.sort_title || a.title).localeCompare(b.sort_title || b.title, "de"));
    if (sort === "year") s.sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
    if (sort === "added") s.sort((a, b) => (b.added ?? "").localeCompare(a.added ?? ""));
    return s;
  }, [data, search, filter, sort]);

  const profileName = (id: number) => profiles.find((p) => p.id === id)?.name ?? "–";

  return (
    <div className="page">
      <PageHeader title="Filme">
        <button className="btn" onClick={() => command("refresh_all")} title="Metadaten aller Filme und Serien aktualisieren">
          <RefreshCw size={15} /> Alle aktualisieren
        </button>
        <Link to="/movies/add" className="btn btn-primary">
          <Plus size={16} /> Film hinzufügen
        </Link>
      </PageHeader>
      <LibraryToolbar view={view} setView={setView} filter={filter} setFilter={setFilter} sort={sort} setSort={setSort} search={search} setSearch={setSearch} count={list.length} />
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && (
        <Empty icon={<Film size={36} />} title="Noch keine Filme">
          <Link to="/movies/add" className="btn btn-primary">
            <Plus size={16} /> Ersten Film hinzufügen
          </Link>
        </Empty>
      )}
      {data && data.length > 0 && list.length === 0 && <Empty title="Keine Treffer für diesen Filter" />}
      {view === "grid" ? (
        <div className="poster-grid">
          {list.map((m) => (
            <MovieCard key={m.id} m={m} />
          ))}
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
                  <th>Profil</th>
                  <th>Verfügbarkeit</th>
                  <th>Datei</th>
                  <th className="num">Größe</th>
                  <th>Hinzugefügt</th>
                </tr>
              </thead>
              <tbody>
                {list.map((m) => (
                  <tr key={m.id}>
                    <td title={m.monitored ? "Überwacht" : "Nicht überwacht"}>{m.monitored ? <Bookmark size={15} className="accent" /> : <BookmarkX size={15} className="muted" />}</td>
                    <td>
                      <Link to={`/movies/${m.id}`} className="strong">
                        {m.title}
                      </Link>
                    </td>
                    <td>{m.year ?? "–"}</td>
                    <td>{MOVIE_STATUS_LABELS[m.status] ?? m.status}</td>
                    <td>{profileName(m.quality_profile_id)}</td>
                    <td>{AVAILABILITY_LABELS[m.minimum_availability] ?? m.minimum_availability}</td>
                    <td>{m.file ? <Badge tone="success">{m.file.quality}</Badge> : <Badge tone={m.monitored ? "danger" : "muted"}>fehlt</Badge>}</td>
                    <td className="num">{m.file ? fmtSize(m.file.size) : "–"}</td>
                    <td>{fmtDate(m.added)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}

function MovieCard({ m }: { m: Movie }) {
  const state = m.has_file ? "has-file" : m.monitored ? (m.status === "released" ? "missing" : "upcoming") : "unmonitored";
  return (
    <Link to={`/movies/${m.id}`} className={`poster-card state-${state}`} title={m.title}>
      <Poster src={m.images?.poster} title={m.title} />
      <div className="poster-card-status">
        {m.has_file ? <CheckCircle2 size={14} /> : <CircleDashed size={14} />}
        {!m.monitored && <BookmarkX size={14} />}
      </div>
      <div className="poster-card-bar" />
      <div className="poster-card-info">
        <div className="poster-card-title">{m.title}</div>
        <div className="poster-card-sub">
          {m.year ?? ""} {m.file ? `· ${m.file.quality}` : ""}
        </div>
      </div>
    </Link>
  );
}
