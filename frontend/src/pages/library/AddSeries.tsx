import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Plus } from "lucide-react";
import { api, errorMessage } from "../../api";
import { useProfiles, useRootFolders, useStored } from "../../hooks";
import { Empty, ErrorBox, Field, PageHeader, Select, Spinner, Toggle } from "../../components/ui";
import { Poster, SourceBadges } from "../../components/Media";
import { Modal } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { useToast } from "../../components/Toast";
import { MONITOR_OPTIONS } from "../../format";
import { profileOptions, rootFolderOptions } from "./common";
import { LookupCard, lookupSources, parentDir } from "./AddMovie";
import type { LookupResult, SeriesType } from "../../types";

export const EPISODE_SOURCE_OPTIONS = [
  { value: "", label: "Automatisch (Provider-Reihenfolge)" },
  { value: "tvdb", label: "TheTVDB" },
  { value: "tmdb", label: "TMDB" },
  { value: "tvmaze", label: "TVmaze" },
  { value: "anilist", label: "AniList" },
];

export const SERIES_TYPE_OPTIONS: { value: SeriesType; label: string }[] = [
  { value: "standard", label: "Standard (S01E01)" },
  { value: "daily", label: "Täglich (Datum)" },
  { value: "anime", label: "Anime (absolute Nummer)" },
];

export function AddSeries() {
  const [params, setParams] = useSearchParams();
  const [term, setTerm] = useState(params.get("term") ?? "");
  const q = params.get("term") ?? "";
  const { data, isFetching, error } = useQuery({
    queryKey: ["lookup", "series", q],
    queryFn: () => api.lookupSeries(q),
    enabled: q.trim().length > 0,
    staleTime: 300_000,
  });
  const [adding, setAdding] = useState<LookupResult | null>(null);

  return (
    <div className="page">
      <PageHeader title="Serie hinzufügen" />
      <form
        className="lookup-form"
        onSubmit={(e) => {
          e.preventDefault();
          setParams(term.trim() ? { term: term.trim() } : {});
        }}
      >
        <div className="search-box search-box-lg">
          <Search size={18} />
          <input className="input" autoFocus value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Serientitel, tvdb:81189, tmdb:1396, tvmaze:169 oder imdb:tt0903747" aria-label="Serie suchen" />
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
      {!isFetching && data && data.length === 0 && <Empty title={`Keine Ergebnisse für „${q}“`}>Tipp: Mit tvdb:ID, tmdb:ID oder tvmaze:ID direkt suchen.</Empty>}
      <div className="lookup-results">
        {data?.map((r, i) => (
          <LookupCard key={`${r.ids.tvdb ?? r.ids.tmdb ?? r.ids.tvmaze ?? r.title}-${i}`} r={r} kind="series" onAdd={() => setAdding(r)} />
        ))}
      </div>
      {adding && <AddSeriesDialog item={adding} onClose={() => setAdding(null)} />}
    </div>
  );
}

export function AddSeriesDialog({ item, path, rootFolder, onClose, onAdded }: { item: LookupResult; path?: string; rootFolder?: string; onClose: () => void; onAdded?: (id: number) => void }) {
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const [lastRoot, setLastRoot] = useStored("mc-add-series-root", "");
  const [lastProfile, setLastProfile] = useStored("mc-add-series-profile", 0);
  const [lastMonitor, setLastMonitor] = useStored("mc-add-series-monitor", "all");
  const [type, setType] = useState<SeriesType>(item.is_anime ? "anime" : "standard");
  const [root, setRoot] = useState("");
  const [profile, setProfile] = useState(0);
  const [monitor, setMonitor] = useState(lastMonitor);
  const [seasonFolder, setSeasonFolder] = useState(true);
  const [source, setSource] = useState("");
  const [tags, setTags] = useState<number[]>([]);
  const [search, setSearch] = useState(!path);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  const nav = useNavigate();

  const rootOpts = rootFolderOptions(roots, type === "anime" ? ["anime", "series"] : ["series", "anime"]);
  useEffect(() => {
    if ((!root || !rootOpts.some((o) => o.value === root)) && rootOpts.length) {
      const preferred = type === "anime" ? roots.find((r) => r.media_type === "anime")?.path : undefined;
      setRoot(preferred ?? rootOpts.find((o) => o.value === lastRoot)?.value ?? rootOpts[0].value);
    }
  }, [rootOpts, root, lastRoot, type, roots]);
  useEffect(() => {
    if (!profile && profiles.length) setProfile(profiles.find((p) => p.id === lastProfile)?.id ?? profiles[0].id);
  }, [profiles, profile, lastProfile]);

  const submit = async () => {
    setBusy(true);
    try {
      const s = await api.addSeries({
        ids: item.ids,
        quality_profile_id: profile,
        root_folder: path ? rootFolder ?? parentDir(path) : root,
        monitored: monitor !== "none",
        monitor,
        series_type: type,
        season_folder: seasonFolder,
        tags,
        episode_source: source,
        search,
        path,
      });
      setLastRoot(root);
      setLastProfile(profile);
      setLastMonitor(monitor);
      toast.success("Serie hinzugefügt", `${s.title}${search ? " – Suche nach fehlenden Episoden gestartet" : ""}`);
      qc.invalidateQueries({ queryKey: ["series"] });
      qc.invalidateQueries({ queryKey: ["lookup"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (onAdded) onAdded(s.id);
      else nav(`/series/${s.id}`);
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
            {busy ? <Spinner size={15} /> : <Plus size={16} />} Serie hinzufügen
          </button>
        </>
      }
    >
      <div className="add-dialog-head">
        <Poster src={item.images?.poster} title={item.title} kind="series" className="poster-sm" />
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
        <Field label="Root-Folder" help={rootOpts.length === 0 ? <span className="tone-text-warning">Kein Root-Folder für Serien/Anime – unter Einstellungen › Medienverwaltung anlegen.</span> : undefined}>
          <Select value={root} onValue={setRoot} options={rootOpts.length ? rootOpts : [{ value: "", label: "– kein Root-Folder –" }]} />
        </Field>
      )}
      <Field label="Überwachen">
        <Select value={monitor} onValue={setMonitor} options={MONITOR_OPTIONS} />
      </Field>
      <Field label="Qualitätsprofil">
        <Select value={profile} onValue={setProfile} options={profileOptions(profiles)} />
      </Field>
      <Field label="Serientyp">
        <Select<SeriesType> value={type} onValue={setType} options={SERIES_TYPE_OPTIONS} />
      </Field>
      <Field label="Episodenquelle" help="Provider, dessen Staffel-/Episodennummerierung verwendet wird. Leer = automatisch.">
        <Select value={source} onValue={setSource} options={EPISODE_SOURCE_OPTIONS} />
      </Field>
      <Field label="Tags">
        <TagSelect value={tags} onChange={setTags} />
      </Field>
      <div className="row gap wrap mt">
        <Toggle checked={seasonFolder} onChange={setSeasonFolder} label="Staffelordner" />
        <Toggle checked={search} onChange={setSearch} label="Fehlende sofort suchen" />
      </div>
    </Modal>
  );
}
