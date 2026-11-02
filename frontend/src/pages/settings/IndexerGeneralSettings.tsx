import { ErrorBox, Field, Loading, NumberInput, Toggle, ChipInput } from "../../components/ui";
import { SaveBar, Section, useSection } from "./common";
import type { IndexerSettings } from "../../types";

export function IndexerGeneralSettings() {
  const { draft, set, save, reset, dirty, saving, isLoading, error } = useSection("indexers");
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !draft) return <Loading />;
  const d = draft as IndexerSettings;
  return (
    <div className="settings-page">
      <Section title="RSS & Suche">
        <div className="form-grid">
          <Field label="RSS-Sync-Intervall (min)" help="0 = deaktiviert. Jeder Sync kostet pro Indexer eine Query.">
            <NumberInput value={d.rss_interval_minutes} onValue={(v) => set("rss_interval_minutes", v)} min={0} />
          </Field>
          <Field label="Live-Limits abfragen (min)" help="Holt die Zähler des Indexers (z. B. TreasureMaps: Grabs der letzten 24 h, auch von anderen Tools). Kostet eine Query, nie einen Grab; entfällt, wenn Suche/RSS die Werte schon frisch geliefert haben. 0 = nur aus normalen Anfragen.">
            <NumberInput value={d.limits_poll_minutes ?? 15} onValue={(v) => set("limits_poll_minutes", v)} min={0} />
          </Field>
          <Field label="Mindestalter (min)" help="Usenet: Releases erst nach dieser Zeit laden (Propagation)">
            <NumberInput value={d.minimum_age_minutes} onValue={(v) => set("minimum_age_minutes", v)} min={0} />
          </Field>
          <Field label="Retention (Tage)" help="Usenet: ältere Releases ablehnen (0 = unbegrenzt)">
            <NumberInput value={d.retention_days} onValue={(v) => set("retention_days", v)} min={0} />
          </Field>
          <Field label="Maximale Größe (MB)" help="0 = unbegrenzt">
            <NumberInput value={d.maximum_size_mb} onValue={(v) => set("maximum_size_mb", v)} min={0} />
          </Field>
        </div>
      </Section>
      <Section title="Kontingente" help="Steuert, ob automatische Vorgänge die Indexer-Limits beachten. Interaktive Aktionen dürfen immer bis zum Limit (inkl. Reserve) gehen.">
        <div className="col gap-sm">
          <Toggle checked={d.rss_respect_limits} onChange={(v) => set("rss_respect_limits", v)} label="RSS-Sync beachtet Query-Limits" />
          <Toggle checked={d.search_respect_limits} onChange={(v) => set("search_respect_limits", v)} label="Automatische Suchen beachten Query-Limits" />
        </div>
        <Field label="Backoff bei Fehlern (min)" help="Pausen-Stufen nach aufeinanderfolgenden Fehlern">
          <ChipInput values={d.backoff_minutes ?? []} numeric onChange={(v) => set("backoff_minutes", v as number[])} />
        </Field>
      </Section>
      <SaveBar dirty={dirty} saving={saving} onSave={() => save()} onReset={reset} />
    </div>
  );
}
