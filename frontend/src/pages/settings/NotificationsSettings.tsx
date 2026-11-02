import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Save, Send, Bell } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Field, Loading, Spinner, TextInput, Toggle } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { useApiMutation } from "../../hooks";
import { Section } from "./common";
import type { Notification, NotificationBase, NotificationSchema } from "../../types";

const KIND_LABELS: Record<string, string> = { webhook: "Webhook", discord: "Discord", gotify: "Gotify", ntfy: "ntfy", telegram: "Telegram", jellyfin: "Jellyfin", emby: "Emby", plex: "Plex" };
const FIELD_LABELS: Record<string, string> = { url: "URL", method: "HTTP-Methode", webhook_url: "Webhook-URL", username: "Benutzername", token: "Token", priority: "Priorität", topic: "Topic", bot_token: "Bot-Token", chat_id: "Chat-ID", api_key: "API-Key" };
const FIELD_HINTS: Record<string, string> = { method: "POST oder PUT", priority: "z. B. 5", url: "https://…" };
const EVENTS: [keyof NotificationBase, string][] = [
  ["on_grab", "Bei Grab"],
  ["on_import", "Bei Import"],
  ["on_upgrade", "Bei Upgrade"],
  ["on_failure", "Bei Fehlschlag"],
  ["on_health", "Bei Health-Problemen"],
];

export function NotificationsSettings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["notifications"], queryFn: api.notifications });
  const schema = useQuery({ queryKey: ["notification-schema"], queryFn: api.notificationSchema, staleTime: Infinity });
  const [editing, setEditing] = useState<{ n?: Notification; kind: string } | null>(null);
  const [picking, setPicking] = useState(false);
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteNotification(id), { invalidate: [["notifications"]], success: "Benachrichtigung gelöscht" });

  return (
    <div className="settings-page">
      <Section
        title="Benachrichtigungen"
        help="Webhooks, Chat-Dienste und Mediaserver-Bibliotheksaktualisierung."
        actions={
          <button className="btn btn-primary" onClick={() => setPicking(true)}>
            <Plus size={15} /> Hinzufügen
          </button>
        }
      >
        {isLoading && <Loading />}
        {error ? <ErrorBox error={error} /> : null}
        {data?.length === 0 && <Empty icon={<Bell size={32} />} title="Keine Benachrichtigungen" />}
        <div className="card-grid">
          {data?.map((n) => (
            <div className={`mini-card ${n.enabled ? "" : "disabled"}`} key={n.id}>
              <div className="mini-card-head">
                <h4>{n.name}</h4>
                <div className="row gap-xs">
                  <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing({ n, kind: n.kind })}>
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-btn danger"
                    title="Löschen"
                    aria-label="Löschen"
                    onClick={async () => {
                      if (await confirm({ title: "Benachrichtigung löschen?", message: `„${n.name}“ löschen?`, confirmLabel: "Löschen", danger: true })) del.mutate(n.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              <div className="muted small">{KIND_LABELS[n.kind] ?? n.kind}</div>
              <div className="chips mt-sm">
                {EVENTS.filter(([k]) => n[k]).map(([k, l]) => (
                  <Badge key={k} tone="info">
                    {l}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>
      {picking && (
        <Modal title="Typ wählen" onClose={() => setPicking(false)}>
          <div className="kind-grid">
            {(schema.data ?? []).map((s) => (
              <button
                key={s.kind}
                className="kind-btn"
                onClick={() => {
                  setPicking(false);
                  setEditing({ kind: s.kind });
                }}
              >
                <Bell size={20} />
                <span>{KIND_LABELS[s.kind] ?? s.kind}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
      {editing && <NotificationDialog n={editing.n} kind={editing.kind} schema={schema.data ?? []} onClose={() => setEditing(null)} />}
    </div>
  );
}

function NotificationDialog({ n, kind, schema, onClose }: { n?: Notification; kind: string; schema: NotificationSchema[]; onClose: () => void }) {
  const fields = schema.find((s) => s.kind === kind)?.fields ?? [];
  const [f, setF] = useState<NotificationBase>(() => ({
    name: n?.name ?? KIND_LABELS[kind] ?? kind,
    kind,
    enabled: n?.enabled ?? true,
    on_grab: n?.on_grab ?? true,
    on_import: n?.on_import ?? true,
    on_upgrade: n?.on_upgrade ?? true,
    on_failure: n?.on_failure ?? true,
    on_health: n?.on_health ?? false,
    settings: { ...(n?.settings ?? {}) },
  }));
  const [testing, setTesting] = useState(false);
  const toast = useToast();
  const save = useApiMutation(() => (n ? api.updateNotification(n.id, f) : api.createNotification(f)), {
    invalidate: [["notifications"]],
    success: "Gespeichert",
    onSuccess: onClose,
  });
  const test = async () => {
    setTesting(true);
    try {
      await api.testNotification(f);
      toast.success("Testnachricht gesendet");
    } catch (e) {
      toast.error("Test fehlgeschlagen", errorMessage(e));
    } finally {
      setTesting(false);
    }
  };
  return (
    <Modal
      title={`${n ? "Bearbeiten" : "Neu"}: ${KIND_LABELS[kind] ?? kind}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn mr-auto" onClick={test} disabled={testing}>
            {testing ? <Spinner size={14} /> : <Send size={15} />} Testen
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
      <Field label="Name">
        <TextInput value={f.name} onValue={(v) => setF({ ...f, name: v })} />
      </Field>
      {fields.map((k) => (
        <Field key={k} label={FIELD_LABELS[k] ?? k}>
          <input
            className={`input ${/token|key/.test(k) ? "mono" : ""}`}
            type={/token|key|password/.test(k) ? "password" : "text"}
            autoComplete="off"
            value={f.settings[k] ?? ""}
            placeholder={FIELD_HINTS[k]}
            onChange={(e) => setF({ ...f, settings: { ...f.settings, [k]: e.target.value } })}
          />
        </Field>
      ))}
      <h4>Ereignisse</h4>
      <div className="col gap-sm">
        {EVENTS.map(([k, l]) => (
          <Toggle key={k} checked={!!f[k]} onChange={(v) => setF({ ...f, [k]: v })} label={l} />
        ))}
        <Toggle checked={f.enabled} onChange={(v) => setF({ ...f, enabled: v })} label="Aktiv" />
      </div>
    </Modal>
  );
}
