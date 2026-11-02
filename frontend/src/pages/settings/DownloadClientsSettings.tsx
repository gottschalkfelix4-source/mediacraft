import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Save, PlugZap, Magnet, Newspaper, FolderOpen, Check, X } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Field, Loading, NumberInput, Spinner, TextInput, Toggle } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { FileBrowser } from "../../components/FileBrowser";
import { TagSelect } from "../../components/TagSelect";
import { useToast } from "../../components/Toast";
import { useApiMutation } from "../../hooks";
import { Section } from "./common";
import type { DownloadClient, DownloadClientBase, DownloadClientSchema, RemotePathMapping } from "../../types";

const KIND_LABELS: Record<string, string> = {
  qbittorrent: "qBittorrent",
  transmission: "Transmission",
  deluge: "Deluge",
  sabnzbd: "SABnzbd",
  nzbget: "NZBGet",
  blackhole_torrent: "Torrent-Blackhole",
  blackhole_usenet: "Usenet-Blackhole",
};

const NEEDS = {
  host: (k: string) => !k.startsWith("blackhole"),
  username: (k: string) => ["qbittorrent", "transmission", "nzbget"].includes(k),
  password: (k: string) => ["qbittorrent", "transmission", "deluge", "nzbget"].includes(k),
  apiKey: (k: string) => k === "sabnzbd",
  categories: (k: string) => !k.startsWith("blackhole"),
  blackhole: (k: string) => k.startsWith("blackhole"),
  directory: (k: string) => k === "transmission",
};

export function DownloadClientsSettings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["downloadclients"], queryFn: api.downloadClients });
  const schema = useQuery({ queryKey: ["downloadclient-schema"], queryFn: api.downloadClientSchema, staleTime: Infinity });
  const [editing, setEditing] = useState<DownloadClient | DownloadClientSchema | null>(null);
  const [picking, setPicking] = useState(false);
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteDownloadClient(id), { invalidate: [["downloadclients"], ["health"]], success: "Downloadclient gelöscht" });
  const toggle = useApiMutation((c: DownloadClient) => api.updateDownloadClient(c.id, { enabled: !c.enabled }), { invalidate: [["downloadclients"]] });

  return (
    <div className="settings-page">
      <Section
        title="Downloadclients"
        actions={
          <button className="btn btn-primary" onClick={() => setPicking(true)}>
            <Plus size={15} /> Client hinzufügen
          </button>
        }
      >
        {isLoading && <Loading />}
        {error ? <ErrorBox error={error} /> : null}
        {data?.length === 0 && <Empty title="Noch kein Downloadclient" />}
        <div className="card-grid">
          {data?.map((c) => (
            <div className={`mini-card ${c.enabled ? "" : "disabled"}`} key={c.id}>
              <div className="mini-card-head">
                <h4>
                  {c.protocol === "torrent" ? <Magnet size={15} className="proto-torrent" /> : <Newspaper size={15} className="proto-usenet" />} {c.name}
                </h4>
                <div className="row gap-xs">
                  <label className="toggle" title={c.enabled ? "Aktiv" : "Deaktiviert"}>
                    <input type="checkbox" checked={c.enabled} onChange={() => toggle.mutate(c)} aria-label="Aktiv" />
                    <span className="toggle-track"><span className="toggle-thumb" /></span>
                  </label>
                  <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing(c)}>
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-btn danger"
                    title="Löschen"
                    aria-label="Löschen"
                    onClick={async () => {
                      if (await confirm({ title: "Downloadclient löschen?", message: `„${c.name}“ löschen?`, confirmLabel: "Löschen", danger: true })) del.mutate(c.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              <div className="muted small">
                {KIND_LABELS[c.kind] ?? c.kind} · Priorität {c.priority}
                {!c.kind.startsWith("blackhole") && ` · ${c.use_ssl ? "https" : "http"}://${c.host}:${c.port}${c.url_base ?? ""}`}
              </div>
              {!c.kind.startsWith("blackhole") && (
                <div className="chips mt-sm">
                  <Badge tone="info">Filme: {c.movie_category || "–"}</Badge>
                  <Badge tone="success">Serien: {c.tv_category || "–"}</Badge>
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>
      <RemotePathMappings />
      {picking && (
        <Modal title="Client-Typ wählen" onClose={() => setPicking(false)}>
          <div className="kind-grid">
            {(schema.data ?? []).map((s) => (
              <button
                key={s.kind}
                className="kind-btn"
                onClick={() => {
                  setPicking(false);
                  setEditing(s);
                }}
              >
                {s.protocol === "torrent" ? <Magnet size={20} className="proto-torrent" /> : <Newspaper size={20} className="proto-usenet" />}
                <span>{KIND_LABELS[s.kind] ?? s.kind}</span>
                <span className="muted small">{s.protocol === "torrent" ? "Torrent" : "Usenet"}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
      {editing && <ClientDialog initial={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ClientDialog({ initial, onClose }: { initial: DownloadClient | DownloadClientSchema; onClose: () => void }) {
  const existing = "id" in initial ? (initial as DownloadClient) : null;
  const kind = initial.kind;
  const [f, setF] = useState<DownloadClientBase>(() => ({
    name: existing?.name ?? KIND_LABELS[kind] ?? kind,
    kind,
    enabled: existing?.enabled ?? true,
    priority: existing?.priority ?? 1,
    host: existing?.host ?? "localhost",
    port: existing?.port ?? (initial as DownloadClientSchema).port ?? 8080,
    use_ssl: existing?.use_ssl ?? false,
    url_base: existing?.url_base ?? (kind === "transmission" ? "/transmission/" : ""),
    username: existing?.username ?? "",
    password: existing?.password ?? "",
    api_key: existing?.api_key ?? "",
    movie_category: existing?.movie_category ?? "movies",
    tv_category: existing?.tv_category ?? "tv",
    remove_completed: existing?.remove_completed ?? false,
    remove_failed: existing?.remove_failed ?? true,
    add_paused: existing?.add_paused ?? false,
    settings: { ...(existing?.settings ?? {}) },
    tags: existing?.tags ?? [],
  }));
  const [browse, setBrowse] = useState<null | "watch_folder" | "completed_folder" | "directory">(null);
  const [testing, setTesting] = useState(false);
  const toast = useToast();
  const set = <K extends keyof DownloadClientBase>(k: K, v: DownloadClientBase[K]) => setF((o) => ({ ...o, [k]: v }));
  const setS = (k: string, v: string | number | boolean) => setF((o) => ({ ...o, settings: { ...o.settings, [k]: v } }));

  const save = useApiMutation(() => (existing ? api.updateDownloadClient(existing.id, f) : api.createDownloadClient(f)), {
    invalidate: [["downloadclients"], ["health"]],
    success: "Downloadclient gespeichert",
    onSuccess: onClose,
  });
  const test = async () => {
    setTesting(true);
    try {
      const r = await api.testDownloadClient({ ...f, id: existing?.id });
      toast.success("Verbindung erfolgreich", typeof r.message === "string" ? r.message : undefined);
    } catch (e) {
      toast.error("Test fehlgeschlagen", errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal
      title={`${existing ? "Bearbeiten" : "Hinzufügen"}: ${KIND_LABELS[kind] ?? kind}`}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn mr-auto" onClick={test} disabled={testing}>
            {testing ? <Spinner size={14} /> : <PlugZap size={15} />} Testen
          </button>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={() => save.mutate(undefined)} disabled={save.isPending || !f.name.trim()}>
            {save.isPending ? <Spinner size={14} /> : <Save size={15} />} Speichern
          </button>
        </>
      }
    >
      <div className="form-grid">
        <Field label="Name">
          <TextInput value={f.name} onValue={(v) => set("name", v)} />
        </Field>
        <Field label="Priorität" help="Kleiner = bevorzugt">
          <NumberInput value={f.priority} onValue={(v) => set("priority", v)} min={1} max={50} />
        </Field>
        {NEEDS.host(kind) && (
          <>
            <Field label="Host">
              <TextInput value={f.host} onValue={(v) => set("host", v)} className="mono" />
            </Field>
            <Field label="Port">
              <NumberInput value={f.port} onValue={(v) => set("port", v)} min={1} max={65535} />
            </Field>
            <Field label="URL-Basis" help={kind === "transmission" ? "Standard: /transmission/" : "Für Reverse-Proxy, sonst leer"}>
              <TextInput value={f.url_base} onValue={(v) => set("url_base", v)} className="mono" />
            </Field>
            <Field label="SSL">
              <Toggle checked={f.use_ssl} onChange={(v) => set("use_ssl", v)} label="HTTPS verwenden" />
            </Field>
          </>
        )}
        {NEEDS.username(kind) && (
          <Field label="Benutzername">
            <TextInput value={f.username} onValue={(v) => set("username", v)} autoComplete="off" />
          </Field>
        )}
        {NEEDS.password(kind) && (
          <Field label="Passwort">
            <input className="input" type="password" autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} />
          </Field>
        )}
        {NEEDS.apiKey(kind) && (
          <Field label="API-Key">
            <TextInput value={f.api_key} onValue={(v) => set("api_key", v)} className="mono" autoComplete="off" />
          </Field>
        )}
        {NEEDS.categories(kind) && (
          <>
            <Field label="Kategorie Filme">
              <TextInput value={f.movie_category} onValue={(v) => set("movie_category", v)} />
            </Field>
            <Field label="Kategorie Serien">
              <TextInput value={f.tv_category} onValue={(v) => set("tv_category", v)} />
            </Field>
          </>
        )}
        {NEEDS.directory(kind) && (
          <Field label="Download-Verzeichnis" help="Basisordner im Client; Kategorie wird als Unterordner angehängt">
            <PathInput value={String(f.settings.directory ?? "")} onChange={(v) => setS("directory", v)} onBrowse={() => setBrowse("directory")} />
          </Field>
        )}
        {NEEDS.blackhole(kind) && (
          <>
            <Field label="Watch-Ordner" help={`Hier werden .${kind === "blackhole_torrent" ? "torrent" : "nzb"}-Dateien abgelegt`}>
              <PathInput value={String(f.settings.watch_folder ?? "")} onChange={(v) => setS("watch_folder", v)} onBrowse={() => setBrowse("watch_folder")} />
            </Field>
            <Field label="Fertig-Ordner" help="Hier legt der externe Client fertige Downloads ab">
              <PathInput value={String(f.settings.completed_folder ?? "")} onChange={(v) => setS("completed_folder", v)} onBrowse={() => setBrowse("completed_folder")} />
            </Field>
          </>
        )}
      </div>
      <div className="col gap-sm mt">
        <Toggle checked={f.enabled} onChange={(v) => set("enabled", v)} label="Aktiv" />
        {!NEEDS.blackhole(kind) && (
          <>
            <Toggle checked={f.add_paused} onChange={(v) => set("add_paused", v)} label="Pausiert hinzufügen" />
            <Toggle checked={f.remove_completed} onChange={(v) => set("remove_completed", v)} label="Nach Import aus Client entfernen" />
            <Toggle checked={f.remove_failed} onChange={(v) => set("remove_failed", v)} label="Fehlgeschlagene entfernen" />
          </>
        )}
      </div>
      <Field label="Tags" help="Nur für Filme/Serien mit diesen Tags verwenden (leer = alle)">
        <TagSelect value={f.tags} onChange={(v) => set("tags", v)} />
      </Field>
      {browse && (
        <FileBrowser
          initial={String(f.settings[browse] ?? "")}
          onClose={() => setBrowse(null)}
          onSelect={(p) => {
            setS(browse, p);
            setBrowse(null);
          }}
        />
      )}
    </Modal>
  );
}

function PathInput({ value, onChange, onBrowse }: { value: string; onChange: (v: string) => void; onBrowse: () => void }) {
  return (
    <div className="row gap-sm">
      <TextInput value={value} onValue={onChange} className="mono grow" />
      <button type="button" className="icon-btn" onClick={onBrowse} title="Durchsuchen" aria-label="Ordner durchsuchen">
        <FolderOpen size={16} />
      </button>
    </div>
  );
}

function RemotePathMappings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["remotepathmappings"], queryFn: api.remotePathMappings });
  const [edit, setEdit] = useState<(Omit<RemotePathMapping, "id"> & { id?: number }) | null>(null);
  const [browse, setBrowse] = useState(false);
  const confirm = useConfirm();
  const save = useApiMutation(
    (m: Omit<RemotePathMapping, "id"> & { id?: number }) => {
      const body = { host: m.host, remote_path: m.remote_path, local_path: m.local_path };
      return m.id ? api.updateRemotePathMapping(m.id, body) : api.createRemotePathMapping(body);
    },
    { invalidate: [["remotepathmappings"]], success: "Mapping gespeichert", onSuccess: () => setEdit(null) },
  );
  const del = useApiMutation((id: number) => api.deleteRemotePathMapping(id), { invalidate: [["remotepathmappings"]], success: "Mapping gelöscht" });

  const row = (m: Omit<RemotePathMapping, "id"> & { id?: number }) => (
    <tr key={m.id ?? "new"} className="edit-row">
      <td>
        <TextInput value={m.host} onValue={(v) => setEdit({ ...m, host: v })} placeholder="Host des Clients (* = alle)" />
      </td>
      <td>
        <TextInput value={m.remote_path} onValue={(v) => setEdit({ ...m, remote_path: v })} placeholder="/downloads/" className="mono" />
      </td>
      <td>
        <div className="row gap-sm">
          <TextInput value={m.local_path} onValue={(v) => setEdit({ ...m, local_path: v })} placeholder="/data/downloads/" className="mono grow" />
          <button className="icon-btn" title="Durchsuchen" aria-label="Lokalen Ordner durchsuchen" onClick={() => setBrowse(true)}>
            <FolderOpen size={15} />
          </button>
        </div>
      </td>
      <td className="actions">
        <button className="icon-btn" title="Speichern" aria-label="Speichern" onClick={() => save.mutate(m)} disabled={!m.host || !m.remote_path || !m.local_path}>
          <Check size={16} />
        </button>
        <button className="icon-btn" title="Abbrechen" aria-label="Abbrechen" onClick={() => setEdit(null)}>
          <X size={16} />
        </button>
      </td>
    </tr>
  );

  return (
    <Section
      title="Remote-Path-Mappings"
      help="Übersetzt Pfade, die der Downloadclient meldet, in Pfade, die MediaCraft sieht (z. B. bei unterschiedlichen Docker-Volumes)."
      actions={
        <button className="btn" onClick={() => setEdit({ host: "", remote_path: "", local_path: "" })} disabled={!!edit}>
          <Plus size={15} /> Mapping
        </button>
      }
    >
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {(data?.length || edit) ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Host</th>
                <th>Remote-Pfad</th>
                <th>Lokaler Pfad</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {data?.map((m) =>
                edit?.id === m.id ? (
                  row(edit)
                ) : (
                  <tr key={m.id}>
                    <td>{m.host}</td>
                    <td className="mono">{m.remote_path}</td>
                    <td className="mono">{m.local_path}</td>
                    <td className="actions">
                      <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEdit(m)}>
                        <Pencil size={15} />
                      </button>
                      <button
                        className="icon-btn danger"
                        title="Löschen"
                        aria-label="Löschen"
                        onClick={async () => {
                          if (await confirm({ title: "Mapping löschen?", message: `${m.remote_path} → ${m.local_path}`, confirmLabel: "Löschen", danger: true })) del.mutate(m.id);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ),
              )}
              {edit && !edit.id && row(edit)}
            </tbody>
          </table>
        </div>
      ) : (
        !isLoading && <div className="muted">Keine Mappings.</div>
      )}
      {browse && edit && (
        <FileBrowser
          initial={edit.local_path}
          onClose={() => setBrowse(false)}
          onSelect={(p) => {
            setEdit({ ...edit, local_path: p });
            setBrowse(false);
          }}
        />
      )}
    </Section>
  );
}
