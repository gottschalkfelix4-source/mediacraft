import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Badge, ErrorBox, Field, Loading, NumberInput, Select, Spinner, Toggle } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { useApiMutation, useTags } from "../../hooks";
import { fmtDuration } from "../../format";
import { Section } from "./common";
import type { DelayProfile } from "../../types";

const PROTOCOL_LABELS = { usenet: "Usenet", torrent: "Torrent" };

function delayLabel(min: number) {
  return min > 0 ? fmtDuration(min * 60) : "sofort";
}

export function DelayProfilesSection() {
  const { data, isLoading, error } = useQuery({ queryKey: ["delayprofiles"], queryFn: api.delayProfiles });
  const { data: tags = [] } = useTags();
  const [editing, setEditing] = useState<Partial<DelayProfile> | null>(null);
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteDelayProfile(id), { invalidate: [["delayprofiles"]], success: "Delay-Profil gelöscht" });
  const tagLabel = (id: number) => tags.find((t) => t.id === id)?.label ?? `#${id}`;

  return (
    <Section
      title="Delay-Profile"
      help="Automatische Grabs (Suche, RSS) warten eine Weile ab dem Veröffentlichungszeitpunkt, damit z. B. noch ein German-DL-Release oder die Usenet-Variante kommen kann. Bei gleicher Qualität gewinnt das bevorzugte Protokoll. Interaktive Grabs warten nie."
      actions={
        <button className="btn btn-primary" onClick={() => setEditing({ tags: [], preferred_protocol: "usenet", usenet_delay: 0, torrent_delay: 0, bypass_highest_quality: true, bypass_min_score: null, enabled: true, order: 1 })}>
          <Plus size={15} /> Neues Delay-Profil
        </button>
      }
    >
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tags</th>
                <th>Bevorzugt</th>
                <th>Usenet</th>
                <th>Torrent</th>
                <th>Sofort bei</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className={p.enabled ? "" : "muted"}>
                  <td>{p.tags.length ? p.tags.map((t) => <Badge key={t}>{tagLabel(t)}</Badge>) : <Badge tone="accent">Standard</Badge>}</td>
                  <td>{PROTOCOL_LABELS[p.preferred_protocol]}</td>
                  <td>{delayLabel(p.usenet_delay)}</td>
                  <td>{delayLabel(p.torrent_delay)}</td>
                  <td className="small">
                    {[p.bypass_highest_quality && "höchster Qualität", p.bypass_min_score != null && `Score ≥ ${p.bypass_min_score}`].filter(Boolean).join(", ") || "–"}
                  </td>
                  <td className="actions">
                    <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing(p)}>
                      <Pencil size={15} />
                    </button>
                    {p.tags.length > 0 && (
                      <button
                        className="icon-btn danger"
                        title="Löschen"
                        aria-label="Löschen"
                        onClick={async () => {
                          if (await confirm({ title: "Delay-Profil löschen?", message: "Betroffene Einträge nutzen danach das Standardprofil.", confirmLabel: "Löschen", danger: true }))
                            del.mutate(p.id);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <DelayEditor initial={editing} onClose={() => setEditing(null)} />}
    </Section>
  );
}

function DelayEditor({ initial, onClose }: { initial: Partial<DelayProfile>; onClose: () => void }) {
  const [p, setP] = useState<Partial<DelayProfile>>(initial);
  const isDefault = !!initial.id && (initial.tags ?? []).length === 0;
  const set = <K extends keyof DelayProfile>(k: K, v: DelayProfile[K]) => setP((x) => ({ ...x, [k]: v }));
  const save = useApiMutation((b: Partial<DelayProfile>) => (b.id ? api.updateDelayProfile(b.id, b) : api.createDelayProfile(b)), {
    invalidate: [["delayprofiles"]],
    success: "Delay-Profil gespeichert",
    onSuccess: onClose,
  });

  return (
    <Modal
      title={isDefault ? "Standard-Delay-Profil" : p.id ? "Delay-Profil bearbeiten" : "Neues Delay-Profil"}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={() => save.mutate(p)} disabled={save.isPending || (!isDefault && !(p.tags ?? []).length)}>
            {save.isPending ? <Spinner size={14} /> : null} Speichern
          </button>
        </>
      }
    >
      <div className="form-grid">
        <Field label="Bevorzugtes Protokoll">
          <Select value={p.preferred_protocol ?? "usenet"} onValue={(v) => set("preferred_protocol", v)} options={[{ value: "usenet", label: "Usenet" }, { value: "torrent", label: "Torrent" }]} />
        </Field>
        <Field label="Usenet-Verzögerung (Minuten)">
          <NumberInput value={p.usenet_delay} onValue={(v) => set("usenet_delay", v)} min={0} />
        </Field>
        <Field label="Torrent-Verzögerung (Minuten)">
          <NumberInput value={p.torrent_delay} onValue={(v) => set("torrent_delay", v)} min={0} />
        </Field>
        <Field label="Sofort laden ab Custom-Format-Score" help="Leer = nie">
          <input
            className="input input-num"
            type="number"
            value={p.bypass_min_score ?? ""}
            onChange={(e) => set("bypass_min_score", e.target.value === "" ? null : Number(e.target.value))}
          />
        </Field>
        {!isDefault && (
          <>
            <Field label="Tags" help="Gilt für Filme und Serien mit einem dieser Tags">
              <TagSelect value={p.tags ?? []} onChange={(v) => set("tags", v)} />
            </Field>
            <Field label="Reihenfolge" help="Bei mehreren passenden Profilen gewinnt die kleinere Zahl">
              <NumberInput value={p.order} onValue={(v) => set("order", v)} />
            </Field>
          </>
        )}
      </div>
      <div className="col gap-sm">
        <Toggle checked={!!p.bypass_highest_quality} onChange={(v) => set("bypass_highest_quality", v)} label="Höchste erlaubte Qualität des Profils sofort laden" />
        {!isDefault && <Toggle checked={p.enabled ?? true} onChange={(v) => set("enabled", v)} label="Aktiv" />}
      </div>
    </Modal>
  );
}
