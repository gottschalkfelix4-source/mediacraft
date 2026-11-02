import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, ArrowUp, ArrowDown, GripVertical, Copy, Save } from "lucide-react";
import { api } from "../../api";
import { Badge, ChipInput, Empty, ErrorBox, Field, Loading, NumberInput, Select, Spinner, TextInput, Toggle } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { useApiMutation, useCustomFormats, useQualities } from "../../hooks";
import { langLabel, LANGUAGES } from "../../format";
import { Section } from "./common";
import type { QualityProfile } from "../../types";

export function ProfilesSettings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const { data: formats = [] } = useCustomFormats();
  const [editing, setEditing] = useState<Partial<QualityProfile> | null>(null);
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteProfile(id), { invalidate: [["profiles"]], success: "Profil gelöscht" });

  return (
    <div className="settings-page">
      <Section
        title="Qualitätsprofile"
        help="Ein Profil legt erlaubte Qualitäten, deren Rangfolge, den Cutoff (ab dem nicht mehr geupgradet wird), Sprachen und Custom-Format-Scores fest."
        actions={
          <button className="btn btn-primary" onClick={() => setEditing({})}>
            <Plus size={15} /> Neues Profil
          </button>
        }
      >
        {isLoading && <Loading />}
        {error ? <ErrorBox error={error} /> : null}
        {data?.length === 0 && <Empty title="Keine Profile" />}
        <div className="card-grid">
          {data?.map((p) => {
            const allowed = p.items.filter((i) => i.allowed).map((i) => i.quality);
            return (
              <div className="mini-card" key={p.id}>
                <div className="mini-card-head">
                  <h4>{p.name}</h4>
                  <div className="row gap-xs">
                    <button className="icon-btn" title="Duplizieren" aria-label="Duplizieren" onClick={() => setEditing({ ...p, id: undefined, name: `${p.name} (Kopie)` })}>
                      <Copy size={15} />
                    </button>
                    <button className="icon-btn" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditing(p)}>
                      <Pencil size={15} />
                    </button>
                    <button
                      className="icon-btn danger"
                      title="Löschen"
                      aria-label="Löschen"
                      onClick={async () => {
                        if (await confirm({ title: "Profil löschen?", message: `„${p.name}“ löschen?`, confirmLabel: "Löschen", danger: true })) del.mutate(p.id);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
                <div className="chips">
                  {allowed
                    .slice()
                    .reverse()
                    .map((q) => (
                      <Badge key={q} tone={q === p.cutoff ? "accent" : "default"} title={q === p.cutoff ? "Cutoff" : undefined}>
                        {q}
                      </Badge>
                    ))}
                </div>
                <div className="muted small mt-sm">
                  Cutoff {p.cutoff} · {p.upgrade_allowed ? "Upgrades an" : "keine Upgrades"}
                  {p.languages.length > 0 && ` · ${p.languages.map(langLabel).join("/")} (${p.language_mode === "require" ? "Pflicht" : "bevorzugt"})`}
                </div>
              </div>
            );
          })}
        </div>
      </Section>
      {editing && <ProfileEditor initial={editing} formats={formats} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ProfileEditor({ initial, formats, onClose }: { initial: Partial<QualityProfile>; formats: { id: number; name: string }[]; onClose: () => void }) {
  const { data: qualities = [] } = useQualities();
  const defaultItems = qualities.filter((q) => !["Unknown", "BR-DISK", "Raw-HD"].includes(q.name)).map((q) => ({ quality: q.name, allowed: ["WEBDL-1080p", "WEBRip-1080p", "Bluray-1080p", "HDTV-1080p"].includes(q.name) }));
  const [p, setP] = useState<Omit<QualityProfile, "id">>(() => ({
    name: initial.name ?? "",
    items: initial.items ?? [],
    cutoff: initial.cutoff ?? "WEBDL-1080p",
    upgrade_allowed: initial.upgrade_allowed ?? true,
    languages: initial.languages ?? [],
    language_mode: initial.language_mode ?? "prefer",
    format_scores: initial.format_scores ?? {},
    min_format_score: initial.min_format_score ?? 0,
    cutoff_format_score: initial.cutoff_format_score ?? 0,
    required_terms: initial.required_terms ?? [],
    ignored_terms: initial.ignored_terms ?? [],
  }));
  const [drag, setDrag] = useState<number | null>(null);
  const items = p.items.length ? p.items : defaultItems;
  // displayed highest first
  const display = [...items].reverse();
  const setDisplay = (d: typeof display) => setP((o) => ({ ...o, items: [...d].reverse() }));
  const move = (i: number, j: number) => {
    if (j < 0 || j >= display.length) return;
    const d = [...display];
    const [x] = d.splice(i, 1);
    d.splice(j, 0, x);
    setDisplay(d);
  };
  const allowed = items.filter((i) => i.allowed).map((i) => i.quality);

  const save = useApiMutation(
    () => {
      const body = { ...p, items, cutoff: allowed.includes(p.cutoff) ? p.cutoff : allowed[allowed.length - 1] ?? p.cutoff };
      return initial.id ? api.updateProfile(initial.id, body) : api.createProfile(body);
    },
    { invalidate: [["profiles"]], success: "Profil gespeichert", onSuccess: onClose },
  );

  return (
    <Modal
      title={initial.id ? `Profil bearbeiten: ${initial.name}` : "Neues Qualitätsprofil"}
      size="xl"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={() => save.mutate(undefined)} disabled={save.isPending || !p.name.trim() || !allowed.length}>
            {save.isPending ? <Spinner size={14} /> : <Save size={15} />} Speichern
          </button>
        </>
      }
    >
      <div className="profile-editor">
        <div>
          <Field label="Name">
            <TextInput value={p.name} onValue={(v) => setP({ ...p, name: v })} autoFocus />
          </Field>
          <Toggle checked={p.upgrade_allowed} onChange={(v) => setP({ ...p, upgrade_allowed: v })} label="Upgrades erlaubt" />
          <Field label="Cutoff" help="Ab dieser Qualität wird nicht mehr geupgradet">
            <Select value={allowed.includes(p.cutoff) ? p.cutoff : ""} onValue={(v) => setP({ ...p, cutoff: v })} options={[...(allowed.includes(p.cutoff) ? [] : [{ value: "", label: "– wählen –" }]), ...allowed.slice().reverse().map((q) => ({ value: q, label: q }))]} />
          </Field>
          <h4 className="mt">Qualitäten</h4>
          <p className="muted small">Höchste Priorität oben. Ziehen oder Pfeile zum Sortieren, Haken = erlaubt.</p>
          <ul className="quality-list">
            {display.map((it, i) => (
              <li
                key={it.quality}
                className={`quality-item ${it.allowed ? "allowed" : ""} ${drag === i ? "dragging" : ""} ${it.quality === p.cutoff ? "cutoff" : ""}`}
                draggable
                onDragStart={(e) => {
                  setDrag(i);
                  e.dataTransfer.effectAllowed = "move";
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (drag !== null && drag !== i) {
                    move(drag, i);
                    setDrag(i);
                  }
                }}
                onDragEnd={() => setDrag(null)}
              >
                <GripVertical size={14} className="muted grip" />
                <label className="checkbox grow">
                  <input type="checkbox" checked={it.allowed} onChange={(e) => setDisplay(display.map((x, k) => (k === i ? { ...x, allowed: e.target.checked } : x)))} />
                  {it.quality}
                </label>
                {it.quality === p.cutoff && <Badge tone="accent">Cutoff</Badge>}
                <button className="icon-btn" disabled={i === 0} onClick={() => move(i, i - 1)} title="Nach oben" aria-label="Nach oben">
                  <ArrowUp size={14} />
                </button>
                <button className="icon-btn" disabled={i === display.length - 1} onClick={() => move(i, i + 1)} title="Nach unten" aria-label="Nach unten">
                  <ArrowDown size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Sprachen</h4>
          <div className="chips mb-sm">
            {LANGUAGES.map((l) => {
              const on = p.languages.includes(l);
              return (
                <button type="button" key={l} className={`chip ${on ? "chip-active" : ""}`} aria-pressed={on} onClick={() => setP({ ...p, languages: on ? p.languages.filter((x) => x !== l) : [...p.languages, l] })}>
                  {langLabel(l)}
                </button>
              );
            })}
          </div>
          <Field label="Sprachmodus" help="Leer = jede Sprache. „Pflicht“ lehnt andere Sprachen ab, „bevorzugt“ sortiert sie nach hinten und erlaubt späteres Upgrade.">
            <Select
              value={p.language_mode}
              onValue={(v) => setP({ ...p, language_mode: v })}
              options={[
                { value: "prefer", label: "Bevorzugen" },
                { value: "require", label: "Pflicht" },
              ]}
            />
          </Field>

          <h4 className="mt">Custom Formats</h4>
          {formats.length === 0 ? (
            <p className="muted small">Noch keine Custom Formats angelegt.</p>
          ) : (
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Format</th>
                  <th className="num">Score</th>
                </tr>
              </thead>
              <tbody>
                {formats.map((f) => (
                  <tr key={f.id}>
                    <td>{f.name}</td>
                    <td className="num">
                      <NumberInput value={p.format_scores[String(f.id)] ?? 0} onValue={(v) => setP({ ...p, format_scores: { ...p.format_scores, [String(f.id)]: v } })} className="input-sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="form-grid mt-sm">
            <Field label="Mindest-Score">
              <NumberInput value={p.min_format_score} onValue={(v) => setP({ ...p, min_format_score: v })} />
            </Field>
            <Field label="Cutoff-Score" help="Upgrade bis dieser Score erreicht ist">
              <NumberInput value={p.cutoff_format_score} onValue={(v) => setP({ ...p, cutoff_format_score: v })} />
            </Field>
          </div>
          <Field label="Pflichtbegriffe" help="Release muss alle enthalten">
            <ChipInput values={p.required_terms} onChange={(v) => setP({ ...p, required_terms: v as string[] })} />
          </Field>
          <Field label="Ausgeschlossene Begriffe" help="Release darf keinen enthalten">
            <ChipInput values={p.ignored_terms} onChange={(v) => setP({ ...p, ignored_terms: v as string[] })} />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
