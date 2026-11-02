import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, UserSearch, RefreshCw, FileEdit, Pencil, Trash2, Bookmark, BookmarkX, FolderOpen, Clock, ExternalLink, FileX } from "lucide-react";
import { api, errorMessage } from "../../api";
import { useApiMutation, useCommand, useProfiles, useTags } from "../../hooks";
import { Badge, Card, ErrorBox, Field, KV, Loading, Select, Tabs, TextInput, Toggle, Spinner } from "../../components/ui";
import { Fanart, Poster, Ratings, SourceBadges, TagList } from "../../components/Media";
import { Modal, useConfirm } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { InteractiveSearch } from "../../components/InteractiveSearch";
import { useToast } from "../../components/Toast";
import { fmtDate, fmtSize, langLabel, AVAILABILITY_LABELS, MOVIE_STATUS_LABELS } from "../../format";
import { HistoryTable } from "./HistoryTable";
import { RenameDialog } from "./RenameDialog";
import { DeleteDialog } from "./DeleteDialog";
import type { MinimumAvailability, Movie } from "../../types";

export function MovieDetail() {
  const id = Number(useParams().id);
  const { data: m, isLoading, error } = useQuery({ queryKey: ["movie", id], queryFn: () => api.movie(id) });
  const { data: profiles = [] } = useProfiles();
  const { data: tags = [] } = useTags();
  const [tab, setTab] = useState<"info" | "history">("info");
  const [dialog, setDialog] = useState<null | "edit" | "delete" | "rename" | "search">(null);
  const command = useCommand();
  const qc = useQueryClient();
  const nav = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();

  const toggleMonitor = useApiMutation((v: boolean) => api.updateMovie(id, { monitored: v }), {
    invalidate: [["movie", id], ["movies"]],
    success: (_r, v) => (v ? "Film wird überwacht" : "Überwachung beendet"),
  });

  if (isLoading) return <Loading />;
  if (error || !m) return <ErrorBox error={error} />;

  const profile = profiles.find((p) => p.id === m.quality_profile_id);

  const deleteFile = async () => {
    if (!m.file) return;
    const ok = await confirm({ title: "Datei löschen?", message: <>Die Datei <code>{m.file.path}</code> wird von der Festplatte gelöscht.</>, confirmLabel: "Löschen", danger: true });
    if (!ok) return;
    try {
      await api.deleteMovieFile(m.id);
      toast.success("Datei gelöscht");
      qc.invalidateQueries({ queryKey: ["movie", id] });
      qc.invalidateQueries({ queryKey: ["movies"] });
    } catch (e) {
      toast.error("Löschen fehlgeschlagen", errorMessage(e));
    }
  };

  const dates: [string, string | null][] = [
    ["Kinostart", m.in_cinemas],
    ["Digital", m.digital_release],
    ["Disc", m.physical_release],
  ];

  return (
    <div className="page page-detail">
      <Fanart src={m.images?.fanart}>
        <Poster src={m.images?.poster} title={m.title} className="poster-lg" />
        <div className="detail-info">
          <div className="detail-title-row">
            <button
              className={`icon-btn monitor-btn ${m.monitored ? "on" : ""}`}
              title={m.monitored ? "Überwacht – klicken zum Beenden" : "Nicht überwacht – klicken zum Überwachen"}
              aria-label="Überwachung umschalten"
              onClick={() => toggleMonitor.mutate(!m.monitored)}
            >
              {m.monitored ? <Bookmark size={22} /> : <BookmarkX size={22} />}
            </button>
            <h1>
              {m.title} {m.year ? <span className="muted">({m.year})</span> : null}
            </h1>
          </div>
          {m.original_title && m.original_title !== m.title && <div className="muted">{m.original_title}</div>}
          <div className="detail-meta">
            {m.runtime ? <span><Clock size={14} /> {m.runtime} min</span> : null}
            {m.certification && <Badge tone="muted">{m.certification}</Badge>}
            <Badge tone={m.status === "released" ? "success" : m.status === "in_cinemas" ? "info" : "muted"}>{MOVIE_STATUS_LABELS[m.status] ?? m.status}</Badge>
            {m.has_file ? <Badge tone="success">{m.file?.quality}</Badge> : <Badge tone={m.monitored ? "danger" : "muted"}>Datei fehlt</Badge>}
            {m.studio && <span>{m.studio}</span>}
            {m.collection && <span>Sammlung: {m.collection}</span>}
          </div>
          {m.genres?.length > 0 && <div className="genres">{m.genres.map((g) => <span key={g} className="genre">{g}</span>)}</div>}
          <Ratings ratings={m.ratings} />
          <p className="detail-overview">{m.overview || <span className="muted">Keine Beschreibung.</span>}</p>
          <div className="detail-facts">
            <span><FolderOpen size={14} /> <span className="mono">{m.path}</span></span>
            <span>Profil: <strong>{profile?.name ?? "–"}</strong></span>
            <span>Verfügbarkeit: <strong>{AVAILABILITY_LABELS[m.minimum_availability]}</strong></span>
            <TagList ids={m.tags} tags={tags} />
          </div>
          <div className="detail-sources">
            <span className="muted small">Metadaten:</span> <SourceBadges sources={m.metadata_sources} />
            {m.tmdb_id && <a className="ext" href={`https://www.themoviedb.org/movie/${m.tmdb_id}`} target="_blank" rel="noreferrer noopener">TMDB <ExternalLink size={11} /></a>}
            {m.imdb_id && <a className="ext" href={`https://www.imdb.com/title/${m.imdb_id}/`} target="_blank" rel="noreferrer noopener">IMDb <ExternalLink size={11} /></a>}
          </div>
        </div>
      </Fanart>

      <div className="action-bar">
        <button className="btn btn-primary" onClick={() => command("movie_search", { movie_id: m.id }, `Suche „${m.title}“`)} title="Automatische Suche">
          <Search size={16} /> Automatische Suche
        </button>
        <button className="btn" onClick={() => setDialog("search")} title="Interaktive Suche">
          <UserSearch size={16} /> Interaktive Suche
        </button>
        <button className="btn" onClick={() => command("refresh_movie", { movie_id: m.id }, `Aktualisierung „${m.title}“`)} title="Metadaten aktualisieren und Ordner scannen">
          <RefreshCw size={16} /> Aktualisieren
        </button>
        <button className="btn" onClick={() => setDialog("rename")} disabled={!m.has_file} title="Datei umbenennen">
          <FileEdit size={16} /> Umbenennen
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
          { key: "info", label: "Übersicht" },
          { key: "history", label: "Verlauf" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "info" ? (
        <div className="detail-grid">
          <Card title="Datei" actions={m.file && <button className="btn btn-sm btn-danger-outline" onClick={deleteFile} title="Datei löschen"><FileX size={14} /> Datei löschen</button>}>
            {m.file ? (
              <KV
                items={[
                  ["Qualität", <><Badge tone="info">{m.file.quality}</Badge>{m.file.proper > 0 && <Badge tone="accent">Proper v{m.file.proper + 1}</Badge>}</>],
                  ["Sprachen", m.file.languages?.map(langLabel).join(", ") || "–"],
                  ["Größe", fmtSize(m.file.size)],
                  ["Release-Gruppe", m.file.release_group || "–"],
                  ["Edition", m.file.edition || "–"],
                  ["Custom-Format-Score", m.file.format_score],
                  ["Release", <span className="break">{m.file.release_name || "–"}</span>],
                  ["Pfad", <span className="mono break">{m.file.path}</span>],
                  ["Hinzugefügt", fmtDate(m.file.added)],
                ]}
              />
            ) : (
              <div className="muted">Keine Datei vorhanden.</div>
            )}
          </Card>
          <Card title="Veröffentlichung">
            <KV items={dates.map(([l, d]) => [l, fmtDate(d)] as [string, string])} />
            <KV
              items={[
                ["Hinzugefügt", fmtDate(m.added)],
                ["Zuletzt aktualisiert", fmtDate(m.last_refresh)],
                ["Originalsprache", m.original_language ?? "–"],
                ["Alternativtitel", m.alt_titles?.length ? <span className="small">{m.alt_titles.slice(0, 8).join(" · ")}</span> : "–"],
              ]}
            />
          </Card>
        </div>
      ) : (
        <Card>
          <MovieHistory id={m.id} />
        </Card>
      )}

      {dialog === "edit" && <EditMovieDialog m={m} onClose={() => setDialog(null)} />}
      {dialog === "delete" && (
        <DeleteDialog
          title={`„${m.title}“ löschen`}
          path={m.path}
          onClose={() => setDialog(null)}
          onConfirm={async (files) => {
            await api.deleteMovie(m.id, files);
            toast.success("Film gelöscht", m.title);
            qc.invalidateQueries({ queryKey: ["movies"] });
            qc.removeQueries({ queryKey: ["movie", id] });
            nav("/movies");
          }}
        />
      )}
      {dialog === "rename" && (
        <RenameDialog
          load={() => api.movieRename(m.id)}
          queryKey={["rename", "movie", m.id]}
          onApply={() => command("rename_movie", { movie_id: m.id }, "Umbenennen")}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "search" && (
        <InteractiveSearch title={`Interaktive Suche: ${m.title}${m.year ? ` (${m.year})` : ""}`} queryKey={["movie", m.id]} fetcher={() => api.movieReleases(m.id)} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}

function MovieHistory({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["history", "movie", id], queryFn: () => api.movieHistory(id) });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  return <HistoryTable records={data ?? []} />;
}

function EditMovieDialog({ m, onClose }: { m: Movie; onClose: () => void }) {
  const { data: profiles = [] } = useProfiles();
  const [profile, setProfile] = useState(m.quality_profile_id);
  const [avail, setAvail] = useState<MinimumAvailability>(m.minimum_availability);
  const [monitored, setMonitored] = useState(m.monitored);
  const [tags, setTags] = useState(m.tags ?? []);
  const [path, setPath] = useState(m.path);
  const [move, setMove] = useState(true);
  const save = useApiMutation(() => api.updateMovie(m.id, { quality_profile_id: profile, minimum_availability: avail, monitored, tags, path, move_files: path !== m.path && move }), {
    invalidate: [["movie", m.id], ["movies"]],
    success: "Gespeichert",
    onSuccess: onClose,
  });
  return (
    <Modal
      title={`Bearbeiten: ${m.title}`}
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
      <Field label="Mindestverfügbarkeit">
        <Select<MinimumAvailability>
          value={avail}
          onValue={setAvail}
          options={[
            { value: "announced", label: "Angekündigt" },
            { value: "in_cinemas", label: "Im Kino" },
            { value: "released", label: "Veröffentlicht" },
          ]}
        />
      </Field>
      <Field label="Pfad">
        <TextInput value={path} onValue={setPath} className="mono" />
      </Field>
      {path !== m.path && (
        <Field label="">
          <Toggle checked={move} onChange={setMove} label="Vorhandene Dateien in den neuen Ordner verschieben" />
        </Field>
      )}
      <Field label="Tags">
        <TagSelect value={tags} onChange={setTags} />
      </Field>
      <Toggle checked={monitored} onChange={setMonitored} label="Überwacht" />
    </Modal>
  );
}
