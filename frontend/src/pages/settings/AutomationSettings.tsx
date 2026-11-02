import { ErrorBox, Field, Loading, NumberInput, Toggle } from "../../components/ui";
import { SaveBar, Section, useSection } from "./common";
import type { DownloadSettings, WantedSettings } from "../../types";

export function AutomationSettings() {
  const wanted = useSection("wanted");
  const downloads = useSection("downloads");
  if (wanted.error || downloads.error) return <ErrorBox error={wanted.error ?? downloads.error} />;
  if (!wanted.draft || !downloads.draft) return <Loading />;
  const w = wanted.draft as WantedSettings;
  const d = downloads.draft as DownloadSettings;
  const dirty = wanted.dirty || downloads.dirty;
  const saving = wanted.saving || downloads.saving;

  return (
    <div className="settings-page">
      <Section title="Gesucht – automatische Suche" help="Regelmäßige Suche nach fehlenden Filmen/Episoden. Verbraucht Indexer-Queries – bei knappen Kontingenten sparsam einstellen.">
        <div className="form-grid">
          <Field label="Suchintervall (Stunden)" help="0 = deaktiviert (nur RSS + manuelle Suchen)">
            <NumberInput value={w.auto_search_interval_hours} onValue={(v) => wanted.set("auto_search_interval_hours", v)} min={0} />
          </Field>
          <Field label="Einträge pro Durchlauf">
            <NumberInput value={w.batch_size} onValue={(v) => wanted.set("batch_size", v)} min={1} />
          </Field>
          <Field label="Mindestabstand pro Eintrag (Stunden)" help="Derselbe Film/dieselbe Episode wird frühestens nach dieser Zeit erneut gesucht">
            <NumberInput value={w.min_hours_between_item_searches} onValue={(v) => wanted.set("min_hours_between_item_searches", v)} min={0} />
          </Field>
        </div>
        <div className="col gap-sm">
          <Toggle checked={w.search_on_add} onChange={(v) => wanted.set("search_on_add", v)} label="Beim Hinzufügen standardmäßig suchen" />
          <Toggle checked={w.cutoff_unmet_search} onChange={(v) => wanted.set("cutoff_unmet_search", v)} label="Automatische Suche schließt „Cutoff nicht erreicht“ ein" />
        </div>
      </Section>
      <Section title="Downloads">
        <div className="col gap-sm mb">
          <Toggle checked={d.completed_handling} onChange={(v) => downloads.set("completed_handling", v)} label="Fertige Downloads automatisch importieren" />
          <Toggle checked={d.redownload_failed} onChange={(v) => downloads.set("redownload_failed", v)} label="Fehlgeschlagene Downloads blocklisten und neu suchen" />
        </div>
        <div className="form-grid">
          <Field label="Prüfintervall (Sekunden)" help="Wie oft die Downloadclients abgefragt werden">
            <NumberInput value={d.check_interval_seconds} onValue={(v) => downloads.set("check_interval_seconds", v)} min={10} />
          </Field>
          <Field label="Hängende Downloads nach (Stunden)" help="Ohne Fortschritt als fehlgeschlagen behandeln (0 = nie)">
            <NumberInput value={d.stalled_timeout_hours} onValue={(v) => downloads.set("stalled_timeout_hours", v)} min={0} />
          </Field>
        </div>
      </Section>
      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={async () => {
          if (wanted.dirty) await wanted.save();
          if (downloads.dirty) await downloads.save();
        }}
        onReset={() => {
          wanted.reset();
          downloads.reset();
        }}
      />
    </div>
  );
}
