import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Eye, Library, Plus, Ban } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Field, Loading, PageHeader, Select, Spinner, Toggle } from "../../components/ui";
import { Modal } from "../../components/Modal";
import { Poster } from "../../components/Media";
import { useToast } from "../../components/Toast";
import { useProfiles, useRootFolders } from "../../hooks";
import { AVAILABILITY_LABELS } from "../../format";
import type { MovieCollection } from "../../types";

export function CollectionsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["collections"], queryFn: api.collections, staleTime: 5 * 60_000 });
  const [adding, setAdding] = useState<{ c: MovieCollection; tmdbIds?: number[] } | null>(null);
  const [filter, setFilter] = useState<"all" | "missing">("missing");
  const list = (data ?? []).filter((c) => filter === "all" || c.missing > 0);

  return (
    <div className="page">
      <PageHeader title="Sammlungen" sub="Filmreihen aus TMDB, zu denen mindestens ein Film in der Bibliothek ist" />
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Filter">
          <button className={`seg-btn ${filter === "missing" ? "active" : ""}`} onClick={() => setFilter("missing")}>
            Mit fehlenden Filmen
          </button>
          <button className={`seg-btn ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
            Alle
          </button>
        </div>
        <span className="muted">{list.length} Sammlungen</span>
      </div>
      {isLoading && <Loading label="Lade Sammlungen von TMDB…" />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && (
        <Empty icon={<Library size={36} />} title="Keine Sammlungen gefunden">
          <p className="muted">Sammlungen erscheinen, sobald Filme mit TMDB-Metadaten aktualisiert wurden, die zu einer Reihe gehören.</p>
        </Empty>
      )}
      <div className="collection-list">
        {list.map((c) => (
          <CollectionCard key={c.id} c={c} onAdd={(tmdbIds) => setAdding({ c, tmdbIds })} />
        ))}
      </div>
      {adding && <AddDialog c={adding.c} tmdbIds={adding.tmdbIds} onClose={() => setAdding(null)} />}
    </div>
  );
}

function CollectionCard({ c, onAdd }: { c: MovieCollection; onAdd: (tmdbIds?: number[]) => void }) {
  return (
    <div className="card collection-card">
      <div className="collection-head">
        <Poster src={c.images.poster} title={c.name} />
        <div className="grow">
          <h3>{c.name}</h3>
          <div className="chips">
            <Badge tone={c.missing ? "warning" : "success"}>
              {c.in_library}/{c.parts.length} in der Bibliothek
            </Badge>
            {c.watch_list_id && (
              <Badge tone="accent" title="Neue Filme dieser Sammlung werden automatisch hinzugefügt">
                <Eye size={12} /> überwacht
              </Badge>
            )}
          </div>
          {c.overview && <p className="muted small clamp-3">{c.overview}</p>}
          <div className="row gap-sm mt-sm">
            {c.missing > 0 && (
              <button className="btn btn-sm btn-primary" onClick={() => onAdd()}>
                <Plus size={14} /> {c.missing} fehlende hinzufügen
              </button>
            )}
            {!c.watch_list_id && <WatchButton c={c} />}
          </div>
        </div>
      </div>
      <div className="collection-parts">
        {c.parts.map((p) => (
          <div key={p.ids.tmdb} className={`collection-part ${p.movie_id ? "in-lib" : ""}`}>
            {p.movie_id ? (
              p.has_file ? <CheckCircle2 size={14} className="tone-text-success" /> : <CircleDashed size={14} className="tone-text-warning" />
            ) : p.excluded ? (
              <Ban size={14} className="muted" />
            ) : (
              <CircleDashed size={14} className="muted" />
            )}
            {p.movie_id ? <Link to={`/movies/${p.movie_id}`}>{p.title}</Link> : <span className={p.excluded ? "muted" : ""}>{p.title}</span>}
            <span className="muted small">{p.year ?? ""}</span>
            {!p.movie_id && (
              <button className="icon-btn small" title="Hinzufügen" aria-label={`${p.title} hinzufügen`} onClick={() => onAdd([p.ids.tmdb])}>
                <Plus size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function WatchButton({ c }: { c: MovieCollection }) {
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const watch = async () => {
    const root = roots.find((r) => r.media_type === "movie");
    if (!profiles[0] || !root) {
      toast.error("Erst ein Qualitätsprofil und einen Film-Root-Folder anlegen");
      return;
    }
    setBusy(true);
    try {
      await api.createImportList({
        name: `Sammlung: ${c.name}`,
        kind: "tmdb_collection",
        media_type: "movie",
        settings: { collection_id: String(c.id) },
        quality_profile_id: profiles[0].id,
        root_folder: root.path,
        monitored: true,
        search_on_add: true,
        enabled: true,
      });
      toast.success("Sammlung wird überwacht", "Neue Filme werden über die Import-Liste hinzugefügt (Profil/Ordner dort anpassbar)");
      qc.invalidateQueries({ queryKey: ["collections"] });
      qc.invalidateQueries({ queryKey: ["importlists"] });
    } catch (e) {
      toast.error("Fehlgeschlagen", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <button className="btn btn-sm" onClick={watch} disabled={busy} title="Künftige Filme dieser Reihe automatisch hinzufügen">
      {busy ? <Spinner size={13} /> : <Eye size={14} />} Überwachen
    </button>
  );
}

function AddDialog({ c, tmdbIds, onClose }: { c: MovieCollection; tmdbIds?: number[]; onClose: () => void }) {
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const movieRoots = roots.filter((r) => r.media_type === "movie");
  const [profile, setProfile] = useState<number>(0);
  const [root, setRoot] = useState("");
  const [availability, setAvailability] = useState("released");
  const [search, setSearch] = useState(true);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const titles = tmdbIds ? c.parts.filter((p) => tmdbIds.includes(p.ids.tmdb)).map((p) => p.title) : c.parts.filter((p) => !p.movie_id && !p.excluded).map((p) => p.title);

  const add = async () => {
    setBusy(true);
    try {
      const r = await api.addCollectionMovies(c.id, {
        tmdb_ids: tmdbIds,
        quality_profile_id: profile || profiles[0]?.id,
        root_folder: root || movieRoots[0]?.path,
        monitored: true,
        minimum_availability: availability,
        search,
      });
      toast.success(`${r.added.length} Film(e) hinzugefügt`, r.added.join(", "));
      if (r.failed.length) toast.error("Nicht alle hinzugefügt", r.failed.join("\n"));
      qc.invalidateQueries({ queryKey: ["collections"] });
      qc.invalidateQueries({ queryKey: ["movies"] });
      onClose();
    } catch (e) {
      toast.error("Hinzufügen fehlgeschlagen", errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${c.name}: hinzufügen`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={add} disabled={busy || !movieRoots.length}>
            {busy ? <Spinner size={14} /> : <Plus size={15} />} {titles.length} hinzufügen
          </button>
        </>
      }
    >
      <p className="small">{titles.join(", ")}</p>
      <div className="form-grid">
        <Field label="Qualitätsprofil">
          <Select value={profile || profiles[0]?.id || 0} onValue={setProfile} options={profiles.map((p) => ({ value: p.id, label: p.name }))} />
        </Field>
        <Field label="Root-Folder">
          <Select value={root || movieRoots[0]?.path || ""} onValue={setRoot} options={movieRoots.map((r) => ({ value: r.path, label: r.path }))} />
        </Field>
        <Field label="Mindestverfügbarkeit">
          <Select value={availability} onValue={setAvailability} options={Object.entries(AVAILABILITY_LABELS).map(([value, label]) => ({ value, label }))} />
        </Field>
      </div>
      <Toggle checked={search} onChange={setSearch} label="Danach suchen" />
    </Modal>
  );
}
