import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Plus, Check, ExternalLink } from "lucide-react";
import { api, errorMessage } from "../../api";
import { useProfiles, useRootFolders, useStored } from "../../hooks";
import { Empty, ErrorBox, Field, PageHeader, Select, Spinner, Toggle, Badge } from "../../components/ui";
import { Poster, SourceBadges } from "../../components/Media";
import { Modal } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { useToast } from "../../components/Toast";
import { profileOptions, rootFolderOptions } from "./common";
import type { LookupResult, MinimumAvailability } from "../../types";

export function parentDir(p: string): string {
  return p.replace(/[\\/]+$/, "").replace(/[\\/][^\\/]*$/, "") || p;
}

export function lookupSources(r: LookupResult): string[] {
  return r.sources ?? r.metadata_sources ?? (r.provider ? [r.provider] : []);
}

export function AddMovie() {
  const [params, setParams] = useSearchParams();
  const [term, setTerm] = useState(params.get("term") ?? "");
  const q = params.get("term") ?? "";
  const { data, isFetching, error } = useQuery({
    queryKey: ["lookup", "movie", q],
    queryFn: () => api.lookupMovie(q),
    enabled: q.trim().length > 0,
    staleTime: 300_000,
  });
  const [adding, setAdding] = useState<LookupResult | null>(null);

  return (
    <div className="page">
      <PageHeader title="Film hinzufügen" />
      <form
        className="lookup-form"
        onSubmit={(e) => {
          e.preventDefault();
          setParams(term.trim() ? { term: term.trim() } : {});
        }}
      >
        <div className="search-box search-box-lg">
          <Search size={18} />
          <input className="input" autoFocus value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Filmtitel, „Titel 2023“, tmdb:603 oder imdb:tt0133093" aria-label="Film suchen" />
        </div>
        <button className="btn btn-primary" type="submit" disabled={!term.trim()}>
          Suchen
        </button>
      </form>
      {isFetching && (
        <div className="loading-block">
          <Spinner size={22} label="Durchsuche Metadaten-Provider…" />
        </div>
      )}
      {error ? <ErrorBox error={error} title="Suche fehlgeschlagen" /> : null}
      {!isFetching && data && data.length === 0 && <Empty title={`Keine Ergebnisse für „${q}“`}>Tipp: Mit tmdb:ID oder imdb:tt… direkt suchen.</Empty>}
      <div className="lookup-results">
        {data?.map((r, i) => (
          <LookupCard key={`${r.ids.tmdb ?? r.ids.imdb ?? r.title}-${i}`} r={r} kind="movie" onAdd={() => setAdding(r)} />
        ))}
      </div>
      {adding && <AddMovieDialog item={adding} onClose={() => setAdding(null)} />}
    </div>
  );
}

export function LookupCard({ r, kind, onAdd }: { r: LookupResult; kind: "movie" | "series"; onAdd: () => void }) {
  const existing = r.existing_id;
  const link = kind === "movie" ? `/movies/${existing}` : `/series/${existing}`;
  const extLinks: [string, string][] = [];
  if (r.ids.tmdb) extLinks.push(["TMDB", `https://www.themoviedb.org/${kind === "movie" ? "movie" : "tv"}/${r.ids.tmdb}`]);
  if (r.ids.imdb) extLinks.push(["IMDb", `https://www.imdb.com/title/${r.ids.imdb}/`]);
  if (r.ids.tvdb) extLinks.push(["TVDB", `https://thetvdb.com/dereferrer/series/${r.ids.tvdb}`]);
  if (r.ids.tvmaze) extLinks.push(["TVmaze", `https://www.tvmaze.com/shows/${r.ids.tvmaze}`]);
  if (r.ids.anilist) extLinks.push(["AniList", `https://anilist.co/anime/${r.ids.anilist}`]);
  return (
    <div className={`lookup-card ${existing ? "existing" : ""}`}>
      <Poster src={r.images?.poster} title={r.title} kind={kind} className="poster-md" />
      <div className="lookup-body">
        <div className="lookup-title">
          <h3>
            {r.title} {r.year ? <span className="muted">({r.year})</span> : null}
          </h3>
          {existing ? (
            <Badge tone="success">
              <Check size={12} /> In der Bibliothek
            </Badge>
          ) : null}
          {r.is_anime && <Badge tone="accent">Anime</Badge>}
        </div>
        {r.original_title && r.original_title !== r.title && <div className="muted small">Originaltitel: {r.original_title}</div>}
        <div className="lookup-meta">
          {r.network && <span>{r.network}</span>}
          {r.runtime ? <span>{r.runtime} min</span> : null}
          {r.genres?.length ? <span>{r.genres.slice(0, 4).join(", ")}</span> : null}
          {r.status && <span>{r.status}</span>}
        </div>
        <p className="lookup-overview">{r.overview || <span className="muted">Keine Beschreibung verfügbar.</span>}</p>
        <div className="lookup-foot">
          <SourceBadges sources={lookupSources(r)} />
          <span className="ext-links">
            {extLinks.map(([l, u]) => (
              <a key={l} href={u} target="_blank" rel="noreferrer noopener" title={`Auf ${l} öffnen`}>
                {l} <ExternalLink size={11} />
              </a>
            ))}
          </span>
          <span className="ml-auto">
            {existing ? (
              <Link to={link} className="btn">
                Öffnen
              </Link>
            ) : (
              <button className="btn btn-primary" onClick={onAdd}>
                <Plus size={16} /> Hinzufügen
              </button>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

export function AddMovieDialog({ item, path, rootFolder, onClose, onAdded }: { item: LookupResult; path?: string; rootFolder?: string; onClose: () => void; onAdded?: (id: number) => void }) {
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const [lastRoot, setLastRoot] = useStored("mc-add-movie-root", "");
  const [lastProfile, setLastProfile] = useStored("mc-add-movie-profile", 0);
  const [lastAvail, setLastAvail] = useStored<MinimumAvailability>("mc-add-movie-avail", "released");
  const [root, setRoot] = useState("");
  const [profile, setProfile] = useState(0);
  const [avail, setAvail] = useState<MinimumAvailability>(lastAvail);
  const [monitored, setMonitored] = useState(true);
  const [tags, setTags] = useState<number[]>([]);
  const [search, setSearch] = useState(!path);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  const nav = useNavigate();
  const rootOpts = rootFolderOptions(roots, ["movie"]);

  useEffect(() => {
    if (!root && rootOpts.length) setRoot(rootOpts.find((o) => o.value === lastRoot)?.value ?? rootOpts[0].value);
  }, [rootOpts, root, lastRoot]);
  useEffect(() => {
    if (!profile && profiles.length) setProfile(profiles.find((p) => p.id === lastProfile)?.id ?? profiles[0].id);
  }, [profiles, profile, lastProfile]);

  const submit = async () => {
    setBusy(true);
    try {
      const m = await api.addMovie({
        ids: item.ids,
        quality_profile_id: profile,
        root_folder: path ? rootFolder ?? parentDir(path) : root,
        monitored,
        minimum_availability: avail,
        tags,
        search,
        path,
      });
      setLastRoot(root);
      setLastProfile(profile);
      setLastAvail(avail);
      toast.success("Film hinzugefügt", `${m.title}${search ? " – Suche gestartet" : ""}`);
      qc.invalidateQueries({ queryKey: ["movies"] });
      qc.invalidateQueries({ queryKey: ["lookup"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (onAdded) onAdded(m.id);
      else nav(`/movies/${m.id}`);
      onClose();
    } catch (e) {
      toast.error("Hinzufügen fehlgeschlagen", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${item.title}${item.year ? ` (${item.year})` : ""} hinzufügen`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy || (!path && !root) || !profile}>
            {busy ? <Spinner size={15} /> : <Plus size={16} />} Film hinzufügen
          </button>
        </>
      }
    >
      <div className="add-dialog-head">
        <Poster src={item.images?.poster} title={item.title} className="poster-sm" />
        <div>
          <p className="lookup-overview clamp-4">{item.overview}</p>
          <SourceBadges sources={lookupSources(item)} />
        </div>
      </div>
      {path ? (
        <Field label="Pfad">
          <code className="mono">{path}</code>
        </Field>
      ) : (
        <Field label="Root-Folder" help={rootOpts.length === 0 ? <span className="tone-text-warning">Kein Root-Folder für Filme – unter Einstellungen › Medienverwaltung anlegen.</span> : undefined}>
          <Select value={root} onValue={setRoot} options={rootOpts.length ? rootOpts : [{ value: "", label: "– kein Root-Folder –" }]} />
        </Field>
      )}
      <Field label="Qualitätsprofil">
        <Select value={profile} onValue={setProfile} options={profileOptions(profiles)} />
      </Field>
      <Field label="Mindestverfügbarkeit" help="Ab wann automatisch gesucht wird">
        <Select<MinimumAvailability>
          value={avail}
          onValue={setAvail}
          options={[
            { value: "announced", label: "Angekündigt" },
            { value: "in_cinemas", label: "Im Kino" },
            { value: "released", label: "Veröffentlicht (digital/Disc)" },
          ]}
        />
      </Field>
      <Field label="Tags">
        <TagSelect value={tags} onChange={setTags} />
      </Field>
      <div className="row gap wrap mt">
        <Toggle checked={monitored} onChange={setMonitored} label="Überwacht" />
        <Toggle checked={search} onChange={setSearch} label="Sofort suchen" />
      </div>
    </Modal>
  );
}
