import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Save, Undo2 } from "lucide-react";
import { api, errorMessage } from "../../api";
import { useSettings } from "../../hooks";
import { useToast } from "../../components/Toast";
import { Spinner } from "../../components/ui";
import type { AllSettings, SettingsSection } from "../../types";

/** Local draft of one settings section with save/reset. */
export function useSection<K extends SettingsSection>(section: K) {
  const { data, isLoading, error } = useSettings();
  const [draft, setDraft] = useState<AllSettings[K] | null>(null);
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();

  useEffect(() => {
    if (data && draft === null) setDraft(structuredClone(data[section]));
  }, [data, draft, section]);

  const dirty = !!data && !!draft && JSON.stringify(data[section]) !== JSON.stringify(draft);
  const set = <F extends keyof AllSettings[K]>(k: F, v: AllSettings[K][F]) => setDraft((d) => (d ? { ...d, [k]: v } : d));
  const save = async (override?: Partial<AllSettings[K]>) => {
    if (!draft) return;
    setSaving(true);
    try {
      const res = await api.saveSettings(section, { ...draft, ...(override ?? {}) });
      qc.setQueryData<AllSettings>(["settings"], (old) => (old ? { ...old, [section]: res } : old));
      setDraft(structuredClone(res));
      toast.success("Einstellungen gespeichert");
      qc.invalidateQueries({ queryKey: ["tasks"] });
      return true;
    } catch (e) {
      toast.error("Speichern fehlgeschlagen", errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  };
  const reset = () => data && setDraft(structuredClone(data[section]));
  return { draft, set, setDraft, save, reset, dirty, saving, isLoading, error };
}

export function SaveBar({ dirty, saving, onSave, onReset }: { dirty: boolean; saving: boolean; onSave: () => void; onReset: () => void }) {
  return (
    <div className={`save-bar ${dirty ? "dirty" : ""}`}>
      {dirty && <span className="muted">Ungespeicherte Änderungen</span>}
      <button className="btn" onClick={onReset} disabled={!dirty || saving}>
        <Undo2 size={15} /> Verwerfen
      </button>
      <button className="btn btn-primary" onClick={onSave} disabled={!dirty || saving}>
        {saving ? <Spinner size={14} /> : <Save size={15} />} Speichern
      </button>
    </div>
  );
}

export function Section({ title, children, help, actions }: { title: string; children: ReactNode; help?: ReactNode; actions?: ReactNode }) {
  return (
    <section className="settings-section">
      <div className="settings-section-head">
        <h3>{title}</h3>
        {actions}
      </div>
      {help && <p className="muted settings-help">{help}</p>}
      {children}
    </section>
  );
}
