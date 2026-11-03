import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Search, Trash2, X } from "lucide-react";
import { api, errorMessage } from "../api";
import { useCommand, useProfiles, useRootFolders } from "../hooks";
import { AVAILABILITY_LABELS, SERIES_TYPE_LABELS } from "../format";
import { DeleteDialog } from "../pages/library/DeleteDialog";
import { Modal } from "./Modal";
import { TagSelect } from "./TagSelect";
import { useToast } from "./Toast";
import { Field, Select, Spinner, Toggle } from "./ui";

export type MassKind = "movie" | "series";

/** Selection state for the library tables. */
export function useSelection() {
  const [ids, setIds] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const setAll = (all: number[], on: boolean) => setIds(on ? new Set(all) : new Set());
  return { ids, toggle, setAll, clear: () => setIds(new Set()) };
}

export function SelectAllBox({ all, selected, onChange }: { all: number[]; selected: Set<number>; onChange: (on: boolean) => void }) {
  const every = all.length > 0 && all.every((id) => selected.has(id));
  return <input type="checkbox" aria-label="Alle auswählen" checked={every} onChange={(e) => onChange(e.target.checked)} />;
}

export function SelectionBar({ kind, ids, onClear }: { kind: MassKind; ids: Set<number>; onClear: () => void }) {
  const [edit, setEdit] = useState(false);
  const [del, setDel] = useState(false);
  const command = useCommand();
  const qc = useQueryClient();
  const toast = useToast();
  const list = [...ids];
  if (list.length === 0) return null;
  const search = () => {
    if (kind === "movie") command("movies_search", { movie_ids: list });
    else list.forEach((id) => command("series_search", { series_id: id }));
  };
  return (
    <>
      <div className="save-bar dirty selection-bar">
        <span className="strong">{list.length} ausgewählt</span>
        <span className="grow" />
        <button className="btn" onClick={search} title="Für alle ausgewählten Einträge suchen">
          <Search size={15} /> Suchen
        </button>
        <button className="btn btn-primary" onClick={() => setEdit(true)}>
          <Pencil size={15} /> Bearbeiten
        </button>
        <button className="btn btn-danger-outline" onClick={() => setDel(true)}>
          <Trash2 size={15} /> Löschen
        </button>
        <button className="icon-btn" onClick={onClear} title="Auswahl aufheben" aria-label="Auswahl aufheben">
          <X size={16} />
        </button>
      </div>
      {edit && <MassEditDialog kind={kind} ids={list} onClose={() => setEdit(false)} onDone={onClear} />}
      {del && (
        <DeleteDialog
          title={`${list.length} ${kind === "movie" ? "Filme" : "Serien"} löschen?`}
          path={`${list.length} Einträge`}
          onClose={() => setDel(false)}
          onConfirm={async (deleteFiles) => {
            const r = kind === "movie" ? await api.bulkDeleteMovies(list, deleteFiles) : await api.bulkDeleteSeries(list, deleteFiles);
            toast.success(`${r.deleted} Einträge gelöscht`);
            qc.invalidateQueries({ queryKey: [kind === "movie" ? "movies" : "series"] });
            setDel(false);
            onClear();
          }}
        />
      )}
    </>
  );
}

const KEEP = "";
type Tri = "" | "true" | "false";

function MassEditDialog({ kind, ids, onClose, onDone }: { kind: MassKind; ids: number[]; onClose: () => void; onDone: () => void }) {
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const qc = useQueryClient();
  const toast = useToast();
  const [monitored, setMonitored] = useState<Tri>(KEEP);
  const [profile, setProfile] = useState<number | "">(KEEP);
  const [root, setRoot] = useState<string>(KEEP);
  const [move, setMove] = useState(true);
  const [availability, setAvailability] = useState<string>(KEEP);
  const [seriesType, setSeriesType] = useState<string>(KEEP);
  const [seasonFolder, setSeasonFolder] = useState<Tri>(KEEP);
  const [editTags, setEditTags] = useState(false);
  const [tags, setTags] = useState<number[]>([]);
  const [tagsMode, setTagsMode] = useState<"add" | "remove" | "replace">("add");
  const [busy, setBusy] = useState(false);

  const triOptions = (yes: string, no: string) => [
    { value: KEEP as Tri, label: "– unverändert –" },
    { value: "true" as Tri, label: yes },
    { value: "false" as Tri, label: no },
  ];
  const rootTypes = kind === "movie" ? ["movie"] : ["series", "anime"];

  const save = async () => {
    const changes: Record<string, unknown> = {};
    if (monitored) changes.monitored = monitored === "true";
    if (profile !== KEEP) changes.quality_profile_id = profile;
    if (root) changes.root_folder = root;
    if (kind === "movie" && availability) changes.minimum_availability = availability;
    if (kind === "series" && seriesType) changes.series_type = seriesType;
    if (kind === "series" && seasonFolder) changes.season_folder = seasonFolder === "true";
    if (editTags) changes.tags = tags;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      const body = { ids, changes, tags_mode: tagsMode, move_files: move };
      const r = kind === "movie" ? await api.bulkUpdateMovies(body) : await api.bulkUpdateSeries(body);
      if (r.errors.length) toast.error(`${r.errors.length} Einträge nicht verschoben`, r.errors.slice(0, 3).join("\n"));
      else toast.success(`${r.updated} Einträge aktualisiert`);
      qc.invalidateQueries({ queryKey: [kind === "movie" ? "movies" : "series"] });
      onDone();
      onClose();
    } catch (e) {
      toast.error("Speichern fehlgeschlagen", errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${ids.length} ${kind === "movie" ? "Filme" : "Serien"} bearbeiten`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? <Spinner size={14} /> : null} Übernehmen
          </button>
        </>
      }
    >
      <div className="form-grid">
        <Field label="Überwacht">
          <Select<Tri> value={monitored} onValue={setMonitored} options={triOptions("Ja", "Nein")} />
        </Field>
        <Field label="Qualitätsprofil">
          <Select<number | "">
            value={profile}
            onValue={setProfile}
            options={[{ value: KEEP as "", label: "– unverändert –" }, ...profiles.map((p) => ({ value: p.id as number | "", label: p.name }))]}
          />
        </Field>
        {kind === "movie" ? (
          <Field label="Mindestverfügbarkeit">
            <Select
              value={availability}
              onValue={setAvailability}
              options={[{ value: KEEP, label: "– unverändert –" }, ...Object.entries(AVAILABILITY_LABELS).map(([value, label]) => ({ value, label }))]}
            />
          </Field>
        ) : (
          <>
            <Field label="Serientyp">
              <Select
                value={seriesType}
                onValue={setSeriesType}
                options={[{ value: KEEP, label: "– unverändert –" }, ...Object.entries(SERIES_TYPE_LABELS).map(([value, label]) => ({ value, label }))]}
              />
            </Field>
            <Field label="Staffelordner">
              <Select<Tri> value={seasonFolder} onValue={setSeasonFolder} options={triOptions("Ja", "Nein")} />
            </Field>
          </>
        )}
        <Field label="Root-Folder" help={root ? undefined : "Ordnernamen bleiben gleich, nur der Root-Folder ändert sich"}>
          <Select
            value={root}
            onValue={setRoot}
            options={[{ value: KEEP, label: "– unverändert –" }, ...roots.filter((r) => rootTypes.includes(r.media_type)).map((r) => ({ value: r.path, label: r.path }))]}
          />
        </Field>
      </div>
      {root && <Toggle checked={move} onChange={setMove} label="Ordner samt Dateien in den neuen Root-Folder verschieben" />}
      <div className="mt">
        <Toggle checked={editTags} onChange={setEditTags} label="Tags ändern" />
        {editTags && (
          <div className="form-grid mt-sm">
            <Field label="Aktion">
              <Select
                value={tagsMode}
                onValue={setTagsMode}
                options={[
                  { value: "add", label: "Hinzufügen" },
                  { value: "remove", label: "Entfernen" },
                  { value: "replace", label: "Ersetzen" },
                ]}
              />
            </Field>
            <Field label="Tags">
              <TagSelect value={tags} onChange={setTags} />
            </Field>
          </div>
        )}
      </div>
    </Modal>
  );
}
