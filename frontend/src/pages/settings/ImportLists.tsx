import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ListPlus, Pencil, Plus, RefreshCw, Trash2, FlaskConical } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Field, Loading, NumberInput, Select, Spinner, TextInput, Toggle } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { useToast } from "../../components/Toast";
import { useApiMutation, useProfiles, useRootFolders } from "../../hooks";
import { AVAILABILITY_LABELS, fmtDateTime, MONITOR_OPTIONS, SERIES_TYPE_LABELS } from "../../format";
import { SaveBar, Section, useSection } from "./common";
import type { ImportList, ImportListSchema, ImportListTest } from "../../types";

export function ImportListsSettings() {
  const lists = useQuery({ queryKey: ["importlists"], queryFn: api.importLists });
  const schema = useQuery({ queryKey: ["importlist-schema"], queryFn: api.importListSchema, staleTime: Infinity });
  const exclusions = useQuery({ queryKey: ["exclusions"], queryFn: api.exclusions });
  const section = useSection("importlists");
  const [editing, setEditing] = useState<Partial<ImportList> | null>(null);
  const confirm = useConfirm();
  const toast = useToast();
  const [syncing, setSyncing] = useState<number | null>(null);
  const del = useApiMutation((id: number) => api.deleteImportList(id), { invalidate: [["importlists"]], success: "Liste gelöscht" });
  const delEx = useApiMutation((id: number) => api.deleteExclusion(id), { invalidate: [["exclusions"]], success: "Ausschluss entfernt" });
  const label = (kind: string) => schema.data?.find((s) => s.kind === kind)?.label ?? kind;

  const sync = async (l: ImportList) => {
    setSyncing(l.id);
    try {
      const r = await api.syncImportList(l.id);
      toast.success(`${l.name}: ${r.added.length} hinzugefügt`, r.added.slice(0, 5).join(", ") || `${r.existing} bereits vorhanden`);
      if (r.failed.length) toast.error(`${r.failed.length} fehlgeschlagen`, r.failed.slice(0, 3).join("\n"));
      lists.refetch();
    } catch (e) {
      toast.error("Synchronisation fehlgeschlagen", errorMessage(e));
      lists.refetch();
    } finally {
      setSyncing(null);
    }
  };

  return (
    <div className="settings-page">
      <Section
        title="Import-Listen"
        help="Filme und Serien aus Listen (TMDB, Trakt, IMDb, Plex-Watchlist oder eigene JSON-URL) werden automatisch hinzugefügt. Was schon in der Bibliothek oder auf der Ausschlussliste steht, wird übersprungen."
        actions={
          <button className="btn btn-primary" onClick={() => setEditing({ kind: "tmdb_list", media_type: "movie", enabled: true, monitored: true, search_on_add: true, monitor: "all", minimum_availability: "released", series_type: "standard", settings: {}, tags: [] })}>
            <Plus size={15} /> Neue Liste
          </button>
        }
      >
        {lists.isLoading && <Loading />}
        {lists.error ? <ErrorBox error={lists.error} /> : null}
        {lists.data?.length === 0 && <Empty icon={<ListPlus size={32} />} title="Keine Import-Listen" />}
        <div className="card-grid">
          {lists.data?.map((l) => (
            <div className={`mini-card ${l.enabled ? "" : "disabled"}`} key={l.id}>
              <div className="mini-card-head">
                <h4>{l.name}</h4>
                <div className="row gap-xs">
                  <button className="icon-btn" title="Jetzt synchronisieren" aria-label="Jetzt synchronisieren" onClick={() => sync(l)} disabled={syncing !== null}>
                    <RefreshCw size={15} className={syncing === l.id ? "spin" : ""} />
                  </button>
                  <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing(l)}>
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-btn danger"
                    title="Löschen"
                    aria-label="Löschen"
                    onClick={async () => {
                      if (await confirm({ title: "Liste löschen?", message: `„${l.name}“ löschen? Bereits hinzugefügte Einträge bleiben.`, confirmLabel: "Löschen", danger: true }))
                        del.mutate(l.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              <div className="chips">
                <Badge tone="accent">{label(l.kind)}</Badge>
                <Badge>{l.media_type === "movie" ? "Filme" : "Serien"}</Badge>
                {!l.enabled && <Badge tone="muted">deaktiviert</Badge>}
              </div>
              <div className="muted small mt-sm">
                {l.last_sync ? `Zuletzt ${fmtDateTime(l.last_sync)}` : "Noch nie synchronisiert"}
                {l.last_result?.items !== undefined && ` · ${l.last_result.items} Einträge, ${l.last_result.added ?? 0} neu`}
              </div>
              {l.last_error && <div className="tone-text-danger small mt-sm">{l.last_error}</div>}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Synchronisation">
        {section.draft ? (
          <>
            <Field label="Intervall (Stunden)" help="0 = nur von Hand">
              <NumberInput value={section.draft.sync_interval_hours} onValue={(v) => section.set("sync_interval_hours", v)} min={0} />
            </Field>
            <SaveBar dirty={section.dirty} saving={section.saving} onSave={() => section.save()} onReset={section.reset} />
          </>
        ) : (
          <Loading />
        )}
      </Section>

      <Section title="Ausschlussliste" help="Diese Titel werden nie über Import-Listen oder Sammlungen hinzugefügt. Einträge entstehen beim Löschen mit „Nicht erneut hinzufügen“.">
        {exclusions.data?.length === 0 && <p className="muted">Keine Ausschlüsse.</p>}
        {exclusions.data && exclusions.data.length > 0 && (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Titel</th>
                  <th>Typ</th>
                  <th>IDs</th>
                  <th>Seit</th>
                  <th className="w-actions" />
                </tr>
              </thead>
              <tbody>
                {exclusions.data.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.title || "–"} {e.year ? `(${e.year})` : ""}
                    </td>
                    <td>{e.media_type === "movie" ? "Film" : "Serie"}</td>
                    <td className="mono small">{[e.tmdb_id && `tmdb:${e.tmdb_id}`, e.tvdb_id && `tvdb:${e.tvdb_id}`, e.imdb_id].filter(Boolean).join(" · ")}</td>
                    <td className="small">{fmtDateTime(e.added)}</td>
                    <td className="actions">
                      <button className="icon-btn danger" title="Entfernen" aria-label="Ausschluss entfernen" onClick={() => delEx.mutate(e.id)}>
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      {editing && schema.data && <ListEditor initial={editing} schema={schema.data} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ListEditor({ initial, schema, onClose }: { initial: Partial<ImportList>; schema: ImportListSchema[]; onClose: () => void }) {
  const [l, setL] = useState<Partial<ImportList>>(initial);
  const [test, setTest] = useState<ImportListTest | null>(null);
  const [testing, setTesting] = useState(false);
  const { data: profiles = [] } = useProfiles();
  const { data: roots = [] } = useRootFolders();
  const toast = useToast();
  const kind = schema.find((s) => s.kind === l.kind) ?? schema[0];
  const set = <K extends keyof ImportList>(k: K, v: ImportList[K]) => {
    setL((x) => ({ ...x, [k]: v }));
    setTest(null);
  };
  const setting = (k: string, v: string) => set("settings", { ...(l.settings ?? {}), [k]: v });
  const media = l.media_type ?? "movie";
  const rootTypes = media === "movie" ? ["movie"] : ["series", "anime"];
  const body = { ...l, quality_profile_id: l.quality_profile_id ?? profiles[0]?.id, root_folder: l.root_folder ?? roots.find((r) => rootTypes.includes(r.media_type))?.path };
  const save = useApiMutation((b: Partial<ImportList>) => (b.id ? api.updateImportList(b.id, b) : api.createImportList(b)), {
    invalidate: [["importlists"]],
    success: "Liste gespeichert",
    onSuccess: onClose,
  });
  const runTest = async () => {
    setTesting(true);
    try {
      setTest(await api.testImportList(body));
    } catch (e) {
      toast.error("Test fehlgeschlagen", errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal
      title={l.id ? "Import-Liste bearbeiten" : "Neue Import-Liste"}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={runTest} disabled={testing}>
            {testing ? <Spinner size={14} /> : <FlaskConical size={15} />} Testen
          </button>
          <span className="grow" />
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={() => save.mutate(body)} disabled={save.isPending || !l.name}>
            {save.isPending ? <Spinner size={14} /> : null} Speichern
          </button>
        </>
      }
    >
      <div className="form-grid">
        <Field label="Name">
          <TextInput value={l.name ?? ""} onValue={(v) => set("name", v)} placeholder="z. B. Meine Watchlist" />
        </Field>
        <Field label="Quelle">
          <Select
            value={l.kind ?? kind.kind}
            onValue={(v) => {
              const k = schema.find((s) => s.kind === v)!;
              setL((x) => ({ ...x, kind: v, media_type: k.media.includes(x.media_type ?? "movie") ? x.media_type : k.media[0] }));
              setTest(null);
            }}
            options={schema.map((s) => ({ value: s.kind, label: s.label }))}
          />
        </Field>
        <Field label="Medientyp">
          <Select value={media} onValue={(v) => set("media_type", v)} options={kind.media.map((m) => ({ value: m, label: m === "movie" ? "Filme" : "Serien" }))} />
        </Field>
        {kind.fields.map((f) => (
          <Field key={f.key} label={f.label} help={f.help || undefined}>
            <TextInput value={l.settings?.[f.key] ?? ""} onValue={(v) => setting(f.key, v)} className="mono" type={f.key === "token" ? "password" : "text"} />
          </Field>
        ))}
        <Field label="Qualitätsprofil">
          <Select value={body.quality_profile_id ?? 0} onValue={(v) => set("quality_profile_id", v)} options={profiles.map((p) => ({ value: p.id, label: p.name }))} />
        </Field>
        <Field label="Root-Folder">
          <Select
            value={body.root_folder ?? ""}
            onValue={(v) => set("root_folder", v)}
            options={roots.filter((r) => rootTypes.includes(r.media_type)).map((r) => ({ value: r.path, label: r.path }))}
          />
        </Field>
        {media === "movie" ? (
          <Field label="Mindestverfügbarkeit">
            <Select value={l.minimum_availability ?? "released"} onValue={(v) => set("minimum_availability", v)} options={Object.entries(AVAILABILITY_LABELS).map(([value, label]) => ({ value, label }))} />
          </Field>
        ) : (
          <>
            <Field label="Überwachen">
              <Select value={l.monitor ?? "all"} onValue={(v) => set("monitor", v)} options={MONITOR_OPTIONS} />
            </Field>
            <Field label="Serientyp">
              <Select value={l.series_type ?? "standard"} onValue={(v) => set("series_type", v)} options={Object.entries(SERIES_TYPE_LABELS).map(([value, label]) => ({ value, label }))} />
            </Field>
          </>
        )}
        <Field label="Tags">
          <TagSelect value={l.tags ?? []} onChange={(v) => set("tags", v)} />
        </Field>
      </div>
      <div className="col gap-sm">
        <Toggle checked={l.enabled ?? true} onChange={(v) => set("enabled", v)} label="Aktiv (automatisch synchronisieren)" />
        <Toggle checked={l.monitored ?? true} onChange={(v) => set("monitored", v)} label="Neue Einträge überwachen" />
        <Toggle checked={l.search_on_add ?? true} onChange={(v) => set("search_on_add", v)} label="Nach dem Hinzufügen suchen" />
      </div>
      {test && (
        <div className="alert mt">
          <strong>{test.items} Einträge</strong> · {test.new_count} neu · {test.existing} vorhanden · {test.excluded} ausgeschlossen
          {test.new.length > 0 && <div className="small muted mt-sm">{test.new.slice(0, 15).join(", ")}{test.new_count > 15 ? " …" : ""}</div>}
        </div>
      )}
    </Modal>
  );
}
