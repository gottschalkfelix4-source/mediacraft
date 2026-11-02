import { useState } from "react";
import { Plus, Pencil, Trash2, Save, FlaskConical, CheckCircle2, XCircle } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Field, Loading, Select, Spinner, TextInput, KV } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { useApiMutation, useCustomFormats } from "../../hooks";
import { useToast } from "../../components/Toast";
import { fmtSize, langLabel } from "../../format";
import { Section } from "./common";
import type { CFCondition, CFTestResult, CustomFormat } from "../../types";

const COND_TYPES: { value: string; label: string; hint: string }[] = [
  { value: "title", label: "Titel (Regex)", hint: "z. B. \\bGerman\\b" },
  { value: "group", label: "Release-Gruppe (Regex)", hint: "z. B. (FLUX|NTb)" },
  { value: "source", label: "Quelle", hint: "webdl, webrip, bluray, remux, hdtv, dvd …" },
  { value: "resolution", label: "Auflösung", hint: "2160p, 1080p, 720p …" },
  { value: "language", label: "Sprache", hint: "german, english, multi …" },
  { value: "codec", label: "Codec", hint: "x265, x264, av1 …" },
  { value: "hdr", label: "HDR", hint: "DV, HDR10, HDR10+ …" },
  { value: "audio", label: "Audio", hint: "TrueHD, Atmos, DTS-HD MA, DDP …" },
  { value: "edition", label: "Edition (Regex)", hint: "Extended|Director" },
  { value: "size", label: "Größe (GB)", hint: "min-max, z. B. 1-15" },
  { value: "indexer_flag", label: "Indexer-Flag", hint: "freeleech, internal …" },
  { value: "protocol", label: "Protokoll", hint: "torrent oder usenet" },
];

export function CustomFormatsSettings() {
  const { data, isLoading, error } = useCustomFormats();
  const [editing, setEditing] = useState<Partial<CustomFormat> | null>(null);
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteCustomFormat(id), { invalidate: [["customformats"], ["profiles"]], success: "Custom Format gelöscht" });

  return (
    <div className="settings-page">
      <Section
        title="Custom Formats"
        help="Ein Format trifft zu, wenn alle Pflicht-Bedingungen passen und je Bedingungstyp mindestens eine der übrigen. Scores werden pro Profil vergeben."
        actions={
          <button className="btn btn-primary" onClick={() => setEditing({ name: "", conditions: [] })}>
            <Plus size={15} /> Neues Format
          </button>
        }
      >
        {isLoading && <Loading />}
        {error ? <ErrorBox error={error} /> : null}
        {data?.length === 0 && <Empty title="Noch keine Custom Formats" />}
        <div className="card-grid">
          {data?.map((f) => (
            <div className="mini-card" key={f.id}>
              <div className="mini-card-head">
                <h4>{f.name}</h4>
                <div className="row gap-xs">
                  <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing(f)}>
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-btn danger"
                    title="Löschen"
                    aria-label="Löschen"
                    onClick={async () => {
                      if (await confirm({ title: "Custom Format löschen?", message: `„${f.name}“ wird gelöscht und aus allen Profilen entfernt.`, confirmLabel: "Löschen", danger: true })) del.mutate(f.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              <div className="chips">
                {f.conditions.map((c, i) => (
                  <Badge key={i} tone={c.negate ? "danger" : c.required ? "accent" : "default"} title={`${c.required ? "Pflicht · " : ""}${c.negate ? "Negiert · " : ""}${c.type}`}>
                    {c.negate ? "¬ " : ""}
                    {c.type}: {c.value}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>
      <ReleaseTester />
      {editing && <FormatEditor initial={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function FormatEditor({ initial, onClose }: { initial: Partial<CustomFormat>; onClose: () => void }) {
  const [name, setName] = useState(initial.name ?? "");
  const [conds, setConds] = useState<CFCondition[]>(
    initial.conditions?.length
      ? initial.conditions.map((c) => ({ type: c.type, value: String(c.value ?? ""), negate: !!c.negate, required: !!c.required }))
      : [{ type: "title", value: "", negate: false, required: false }],
  );
  const save = useApiMutation(
    () => {
      const body = { name, conditions: conds.filter((c) => c.value.trim() !== "").map((c) => ({ ...c, value: c.value.trim() })) };
      return initial.id ? api.updateCustomFormat(initial.id, body) : api.createCustomFormat(body);
    },
    { invalidate: [["customformats"]], success: "Custom Format gespeichert", onSuccess: onClose },
  );
  const upd = (i: number, patch: Partial<CFCondition>) => setConds(conds.map((c, k) => (k === i ? { ...c, ...patch } : c)));
  return (
    <Modal
      title={initial.id ? `Format bearbeiten: ${initial.name}` : "Neues Custom Format"}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={() => save.mutate(undefined)} disabled={save.isPending || !name.trim()}>
            {save.isPending ? <Spinner size={14} /> : <Save size={15} />} Speichern
          </button>
        </>
      }
    >
      <Field label="Name">
        <TextInput value={name} onValue={setName} autoFocus placeholder="z. B. German DL" />
      </Field>
      <h4>Bedingungen</h4>
      <div className="cond-list">
        {conds.map((c, i) => (
          <div className="cond" key={i}>
            <Select value={c.type} onValue={(v) => upd(i, { type: v })} options={COND_TYPES.map((t) => ({ value: t.value, label: t.label }))} aria-label="Typ" />
            <TextInput value={c.value} onValue={(v) => upd(i, { value: v })} placeholder={COND_TYPES.find((t) => t.value === c.type)?.hint} className="mono grow" aria-label="Wert" />
            <label className="checkbox" title="Bedingung umkehren">
              <input type="checkbox" checked={c.negate} onChange={(e) => upd(i, { negate: e.target.checked })} /> Negieren
            </label>
            <label className="checkbox" title="Muss zutreffen">
              <input type="checkbox" checked={c.required} onChange={(e) => upd(i, { required: e.target.checked })} /> Pflicht
            </label>
            <button className="icon-btn danger" onClick={() => setConds(conds.filter((_, k) => k !== i))} title="Bedingung entfernen" aria-label="Bedingung entfernen">
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      <button className="btn btn-sm mt-sm" onClick={() => setConds([...conds, { type: "title", value: "", negate: false, required: false }])}>
        <Plus size={14} /> Bedingung
      </button>
    </Modal>
  );
}

function ReleaseTester() {
  const [title, setTitle] = useState("");
  const [sizeGb, setSizeGb] = useState("");
  const [res, setRes] = useState<CFTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const run = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      setRes(await api.testCustomFormat(title.trim(), Math.round((Number(sizeGb.replace(",", ".")) || 0) * 1024 ** 3)));
    } catch (err) {
      toast.error("Test fehlgeschlagen", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const p = res?.parsed;
  return (
    <Section title="Release testen" help="Prüft, wie ein Release-Titel erkannt wird, welche Formate zutreffen und welchen Score er je Profil erhält.">
      <form className="row gap-sm wrap" onSubmit={run}>
        <input className="input mono grow" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Der.Film.2023.German.DL.2160p.WEB.H265-GROUP" aria-label="Release-Titel" />
        <input className="input input-num" value={sizeGb} onChange={(e) => setSizeGb(e.target.value)} placeholder="Größe GB" aria-label="Größe in GB" />
        <button className="btn btn-primary" type="submit" disabled={busy || !title.trim()}>
          {busy ? <Spinner size={14} /> : <FlaskConical size={15} />} Testen
        </button>
      </form>
      {res && p && (
        <div className="test-result">
          <KV
            items={[
              ["Titel", `${p.title}${p.year ? ` (${p.year})` : ""}`],
              ["Typ", p.is_tv ? `Serie${p.seasons.length ? ` · S${p.seasons.join(",")}` : ""}${p.episodes.length ? ` E${p.episodes.join(",")}` : ""}${p.full_season ? " (Staffelpaket)" : ""}` : "Film"],
              ["Qualität", <Badge tone="info">{p.quality}</Badge>],
              ["Quelle / Auflösung", `${p.source} / ${p.resolution || "?"}p`],
              ["Sprachen", p.languages.map(langLabel).join(", ") || "–"],
              ["Gruppe", p.release_group ?? "–"],
              ["Codec / HDR / Audio", [p.codec, p.hdr.join(" "), p.audio.join(" "), p.audio_channels].filter(Boolean).join(" · ") || "–"],
              ["Edition", p.edition ?? "–"],
              ["Größe", sizeGb ? fmtSize((Number(sizeGb.replace(",", ".")) || 0) * 1024 ** 3) : "–"],
              ["Formate", res.formats.length ? res.formats.map((f) => <Badge key={f} tone="accent">{f}</Badge>) : "keine"],
            ]}
          />
          <table className="table table-compact mt-sm">
            <thead>
              <tr>
                <th>Profil</th>
                <th>Qualität erlaubt</th>
                <th className="num">Score</th>
              </tr>
            </thead>
            <tbody>
              {res.profiles.map((pr) => (
                <tr key={pr.id}>
                  <td>{pr.name}</td>
                  <td>{pr.quality_allowed ? <CheckCircle2 size={15} className="tone-text-success" /> : <XCircle size={15} className="tone-text-danger" />}</td>
                  <td className={`num score ${pr.score > 0 ? "pos" : pr.score < 0 ? "neg" : ""}`}>{pr.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
