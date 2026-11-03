import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { api, errorMessage } from "../../api";
import { ErrorBox, Loading } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { SaveBar, Section } from "./common";
import type { QualityDefinition } from "../../types";

/** Size limits per quality in MB per minute of runtime (90 min film: ×90, 45 min episode: ×45). */
export function QualityDefinitionsSettings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["qualitydefinitions"], queryFn: api.qualityDefinitions });
  const [draft, setDraft] = useState<QualityDefinition[] | null>(null);
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();

  useEffect(() => {
    if (data && !draft) setDraft(structuredClone(data));
  }, [data, draft]);

  if (error) return <ErrorBox error={error} />;
  if (isLoading || !draft || !data) return <Loading />;

  const dirty = JSON.stringify(draft) !== JSON.stringify(data);
  const set = (name: string, k: "min" | "max", v: number) => setDraft((d) => d!.map((q) => (q.name === name ? { ...q, [k]: v } : q)));
  const reset = (name: string) => setDraft((d) => d!.map((q) => (q.name === name ? { ...q, min: q.default_min, max: q.default_max } : q)));
  const save = async () => {
    setSaving(true);
    try {
      const res = await api.saveQualityDefinitions(draft);
      qc.setQueryData(["qualitydefinitions"], res);
      qc.invalidateQueries({ queryKey: ["settings"] });
      setDraft(structuredClone(res));
      toast.success("Qualitätsdefinitionen gespeichert");
    } catch (e) {
      toast.error("Speichern fehlgeschlagen", errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-page">
      <Section
        title="Qualitätsdefinitionen"
        help="Erlaubte Dateigröße je Qualität in MB pro Minute Laufzeit. Releases außerhalb des Bereichs werden abgelehnt. 0 als Maximum = unbegrenzt. Beispiel: 1080p-WEB-DL mit 4–155 MB/min erlaubt für einen 90-Minuten-Film 0,35–13,6 GB."
      >
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Qualität</th>
                <th className="num">Min (MB/min)</th>
                <th className="num">Max (MB/min)</th>
                <th className="num">Film 90 min</th>
                <th className="num">Folge 45 min</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {draft.map((q) => {
                const changed = q.min !== q.default_min || q.max !== q.default_max;
                const range = (mins: number) => `${((q.min * mins) / 1024).toFixed(1)}–${q.max ? ((q.max * mins) / 1024).toFixed(1) : "∞"} GB`;
                return (
                  <tr key={q.name}>
                    <td className={changed ? "strong" : ""}>{q.name}</td>
                    <td className="num">
                      <input className="input input-num" type="number" min={0} step={0.5} value={q.min} onChange={(e) => set(q.name, "min", Number(e.target.value) || 0)} aria-label={`${q.name} Minimum`} />
                    </td>
                    <td className="num">
                      <input className="input input-num" type="number" min={0} step={1} value={q.max} onChange={(e) => set(q.name, "max", Number(e.target.value) || 0)} aria-label={`${q.name} Maximum`} />
                    </td>
                    <td className="num small muted">{range(90)}</td>
                    <td className="num small muted">{range(45)}</td>
                    <td className="actions">
                      {changed && (
                        <button className="icon-btn" title={`Standard: ${q.default_min}–${q.default_max || "∞"}`} aria-label="Auf Standard zurücksetzen" onClick={() => reset(q.name)}>
                          <RotateCcw size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>
      <SaveBar dirty={dirty} saving={saving} onSave={save} onReset={() => setDraft(structuredClone(data))} />
    </div>
  );
}
