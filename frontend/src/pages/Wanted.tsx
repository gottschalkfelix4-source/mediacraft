import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, Film, Tv, SearchCheck } from "lucide-react";
import { api } from "../api";
import { Badge, Empty, ErrorBox, Loading, PageHeader, Tabs, Pager } from "../components/ui";
import { Poster } from "../components/Media";
import { useCommand, useProfiles } from "../hooks";
import { epCode, fmtDate, AVAILABILITY_LABELS } from "../format";
import type { Episode, Movie } from "../types";

type TabKey = "missing" | "cutoff";
const PAGE = 50;

export function WantedPage() {
  const params = useParams();
  const tab: TabKey = params.tab === "cutoff" ? "cutoff" : "missing";
  const nav = useNavigate();
  const command = useCommand();
  const { data, isLoading, error } = useQuery({
    queryKey: ["wanted", tab],
    queryFn: () => (tab === "missing" ? api.wantedMissing() : api.wantedCutoff()),
  });
  const [kind, setKind] = useState<"movies" | "episodes">("movies");
  const [page, setPage] = useState(1);
  const { data: profiles = [] } = useProfiles();

  const counts = { movies: data?.movies.length ?? 0, episodes: data?.episodes.length ?? 0 };
  const episodes = useMemo(() => (data?.episodes ?? []).slice((page - 1) * PAGE, page * PAGE), [data, page]);
  const movies = useMemo(() => (data?.movies ?? []).slice((page - 1) * PAGE, page * PAGE), [data, page]);
  const pages = Math.max(1, Math.ceil(counts[kind] / PAGE));

  return (
    <div className="page">
      <PageHeader title="Gesucht">
        <button
          className="btn btn-primary"
          onClick={() => command(tab === "missing" ? "wanted_search" : "cutoff_search")}
          title={tab === "missing" ? "Alle fehlenden Filme und Episoden suchen (limit-bewusst)" : "Alle Einträge unter Cutoff suchen"}
        >
          <SearchCheck size={16} /> Alle suchen
        </button>
      </PageHeader>
      <Tabs
        tabs={[
          { key: "missing", label: "Fehlend" },
          { key: "cutoff", label: "Cutoff nicht erreicht" },
        ]}
        active={tab}
        onChange={(k) => {
          setPage(1);
          nav(`/wanted/${k}`);
        }}
      />
      <div className="toolbar">
        <div className="seg">
          <button className={`seg-btn ${kind === "movies" ? "active" : ""}`} onClick={() => { setKind("movies"); setPage(1); }}>
            <Film size={14} /> Filme <span className="tab-count">{counts.movies}</span>
          </button>
          <button className={`seg-btn ${kind === "episodes" ? "active" : ""}`} onClick={() => { setKind("episodes"); setPage(1); }}>
            <Tv size={14} /> Episoden <span className="tab-count">{counts.episodes}</span>
          </button>
        </div>
        <span className="ml-auto" />
        <Pager page={page} pages={pages} onPage={setPage} />
      </div>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && kind === "movies" && (counts.movies === 0 ? <Empty title="Keine Filme in dieser Liste" /> : <MovieTable movies={movies} tab={tab} profileName={(id) => profiles.find((p) => p.id === id)?.name ?? "–"} />)}
      {data && kind === "episodes" && (counts.episodes === 0 ? <Empty title="Keine Episoden in dieser Liste" /> : <EpisodeTable episodes={episodes} tab={tab} />)}
    </div>
  );
}

function MovieTable({ movies, tab, profileName }: { movies: Movie[]; tab: TabKey; profileName: (id: number) => string }) {
  const command = useCommand();
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th className="w-poster" />
            <th>Film</th>
            <th>Profil</th>
            <th>{tab === "missing" ? "Verfügbarkeit" : "Aktuelle Qualität"}</th>
            <th>Veröffentlichung</th>
            <th className="w-actions" />
          </tr>
        </thead>
        <tbody>
          {movies.map((m) => (
            <tr key={m.id}>
              <td>
                <Poster src={m.images?.poster} title={m.title} className="poster-xs" />
              </td>
              <td>
                <Link to={`/movies/${m.id}`} className="strong">
                  {m.title}
                </Link>{" "}
                <span className="muted">{m.year ? `(${m.year})` : ""}</span>
              </td>
              <td>{profileName(m.quality_profile_id)}</td>
              <td>{tab === "missing" ? AVAILABILITY_LABELS[m.minimum_availability] : m.file ? <Badge tone="warning">{m.file.quality}</Badge> : "–"}</td>
              <td className="small">{fmtDate(m.digital_release ?? m.physical_release ?? m.in_cinemas)}</td>
              <td className="actions">
                <button className="icon-btn" title="Suchen" aria-label="Film suchen" onClick={() => command("movie_search", { movie_id: m.id }, `Suche „${m.title}“`)}>
                  <Search size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EpisodeTable({ episodes, tab }: { episodes: Episode[]; tab: TabKey }) {
  const command = useCommand();
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Serie</th>
            <th>Episode</th>
            <th>Titel</th>
            <th>Ausstrahlung</th>
            {tab === "cutoff" && <th>Aktuelle Qualität</th>}
            <th className="w-actions" />
          </tr>
        </thead>
        <tbody>
          {episodes.map((e) => (
            <tr key={e.id}>
              <td>
                <Link to={`/series/${e.series_id}`} className="strong">
                  {e.series_title ?? `Serie #${e.series_id}`}
                </Link>
              </td>
              <td className="nowrap">{epCode(e.season, e.number)}</td>
              <td>{e.title ?? <span className="muted">TBA</span>}</td>
              <td className="nowrap">{fmtDate(e.air_date_utc ?? e.air_date)}</td>
              {tab === "cutoff" && <td>{e.file ? <Badge tone="warning">{e.file.quality}</Badge> : "–"}</td>}
              <td className="actions">
                <button
                  className="icon-btn"
                  title="Suchen"
                  aria-label="Episode suchen"
                  onClick={() => command("episode_search", { series_id: e.series_id, episode_ids: [e.id] }, `Suche ${e.series_title ?? ""} ${epCode(e.season, e.number)}`)}
                >
                  <Search size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
