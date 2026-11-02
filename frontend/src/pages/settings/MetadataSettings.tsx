import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, ArrowDown, CheckCircle2, XCircle, Key, Plus, X } from "lucide-react";
import { api } from "../../api";
import { Badge, ErrorBox, Field, Loading, NumberInput, Select, TextInput, Toggle } from "../../components/ui";
import { providerLabel } from "../../format";
import { SaveBar, Section, useSection } from "./common";
import type { MetadataSettings } from "../../types";

const LANGS = [
  { value: "de", label: "Deutsch" },
  { value: "en", label: "Englisch" },
  { value: "fr", label: "Französisch" },
  { value: "es", label: "Spanisch" },
  { value: "it", label: "Italienisch" },
  { value: "nl", label: "Niederländisch" },
  { value: "pl", label: "Polnisch" },
  { value: "pt", label: "Portugiesisch" },
  { value: "ru", label: "Russisch" },
  { value: "ja", label: "Japanisch" },
];

const SUPPORT: Record<string, { movies: boolean; series: boolean }> = {
  tmdb: { movies: true, series: true },
  tvdb: { movies: false, series: true },
  tvmaze: { movies: false, series: true },
  omdb: { movies: true, series: false },
  anilist: { movies: true, series: true },
};

function OrderList({ value, onChange, candidates }: { value: string[]; onChange: (v: string[]) => void; candidates: string[] }) {
  const move = (i: number, j: number) => {
    if (j < 0 || j >= value.length) return;
    const n = [...value];
    const [x] = n.splice(i, 1);
    n.splice(j, 0, x);
    onChange(n);
  };
  const missing = candidates.filter((c) => !value.includes(c));
  return (
    <div>
      <ol className="order-list">
        {value.map((p, i) => (
          <li key={p}>
            <span className="order-num">{i + 1}</span>
            <span className="grow">{providerLabel(p)}</span>
            {i === 0 && <Badge tone="accent">primär</Badge>}
            <button className="icon-btn" disabled={i === 0} onClick={() => move(i, i - 1)} title="Nach oben" aria-label="Nach oben">
              <ArrowUp size={14} />
            </button>
            <button className="icon-btn" disabled={i === value.length - 1} onClick={() => move(i, i + 1)} title="Nach unten" aria-label="Nach unten">
              <ArrowDown size={14} />
            </button>
            <button className="icon-btn danger" onClick={() => onChange(value.filter((x) => x !== p))} title="Entfernen" aria-label="Entfernen">
              <X size={14} />
            </button>
          </li>
        ))}
      </ol>
      {missing.length > 0 && (
        <div className="chips">
          {missing.map((m) => (
            <button key={m} type="button" className="chip" onClick={() => onChange([...value, m])}>
              <Plus size={12} /> {providerLabel(m)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function MetadataSettingsPage() {
  const { draft, set, save, reset, dirty, saving, isLoading, error } = useSection("metadata");
  const providers = useQuery({ queryKey: ["metadata-providers"], queryFn: api.metadataProviders });
  const qc = useQueryClient();
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !draft) return <Loading />;
  const d = draft as MetadataSettings;
  const all = Object.keys(SUPPORT);

  return (
    <div className="settings-page">
      <Section title="Provider-Status" help="TVmaze und AniList funktionieren ohne API-Key – Serien und Anime lassen sich also sofort hinzufügen. Für Filme wird ein TMDB-Key empfohlen (kostenlos auf themoviedb.org).">
        {providers.isLoading && <Loading />}
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Filme</th>
                <th>Serien</th>
                <th>Key nötig</th>
                <th>Aktiviert</th>
                <th>Verfügbar</th>
              </tr>
            </thead>
            <tbody>
              {providers.data?.map((p) => (
                <tr key={p.name}>
                  <td className="strong">{providerLabel(p.name)}</td>
                  <td>{p.movies ? <CheckCircle2 size={15} className="tone-text-success" /> : <span className="muted">–</span>}</td>
                  <td>{p.series ? <CheckCircle2 size={15} className="tone-text-success" /> : <span className="muted">–</span>}</td>
                  <td>{p.needs_key ? <Key size={14} /> : <span className="muted">nein</span>}</td>
                  <td>
                    <Toggle checked={d.enabled[p.name] ?? true} onChange={(v) => set("enabled", { ...d.enabled, [p.name]: v })} />
                  </td>
                  <td>
                    {p.available ? (
                      <Badge tone="success">bereit</Badge>
                    ) : (
                      <Badge tone="warning" title={p.needs_key ? "API-Key fehlt" : undefined}>
                        <XCircle size={12} /> {p.needs_key ? "Key fehlt" : "nicht verfügbar"}
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="API-Keys">
        <div className="form-grid">
          <Field label="TMDB API-Key (v3) oder Read-Access-Token" help={<a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noreferrer noopener">themoviedb.org/settings/api</a>}>
            <TextInput value={d.keys.tmdb} onValue={(v) => set("keys", { ...d.keys, tmdb: v })} className="mono" autoComplete="off" />
          </Field>
          <Field label="TheTVDB API-Key (v4)" help={<a href="https://thetvdb.com/api-information" target="_blank" rel="noreferrer noopener">thetvdb.com/api-information</a>}>
            <TextInput value={d.keys.tvdb} onValue={(v) => set("keys", { ...d.keys, tvdb: v })} className="mono" autoComplete="off" />
          </Field>
          <Field label="TheTVDB PIN" help="Nur bei Abonnenten-Keys nötig">
            <TextInput value={d.keys.tvdb_pin} onValue={(v) => set("keys", { ...d.keys, tvdb_pin: v })} className="mono" autoComplete="off" />
          </Field>
          <Field label="OMDb API-Key" help={<a href="https://www.omdbapi.com/apikey.aspx" target="_blank" rel="noreferrer noopener">omdbapi.com</a>}>
            <TextInput value={d.keys.omdb} onValue={(v) => set("keys", { ...d.keys, omdb: v })} className="mono" autoComplete="off" />
          </Field>
        </div>
      </Section>

      <Section title="Sprache">
        <div className="form-grid">
          <Field label="Metadaten-Sprache">
            <Select value={d.language} onValue={(v) => set("language", v)} options={LANGS} />
          </Field>
          <Field label="Fallback-Sprache" help="Wenn kein Text in der Hauptsprache existiert">
            <Select value={d.fallback_language} onValue={(v) => set("fallback_language", v)} options={LANGS} />
          </Field>
        </div>
      </Section>

      <Section title="Provider-Reihenfolge" help="Der erste verfügbare Provider liefert die Grunddaten (bei Serien die Episodenliste), die folgenden ergänzen fehlende Felder, IDs, Bilder und Bewertungen.">
        <div className="order-grid">
          <Field label="Filme">
            <OrderList value={d.movie_providers} onChange={(v) => set("movie_providers", v)} candidates={all.filter((p) => SUPPORT[p].movies)} />
          </Field>
          <Field label="Serien">
            <OrderList value={d.series_providers} onChange={(v) => set("series_providers", v)} candidates={all.filter((p) => SUPPORT[p].series)} />
          </Field>
          <Field label="Anime">
            <OrderList value={d.anime_providers} onChange={(v) => set("anime_providers", v)} candidates={all.filter((p) => SUPPORT[p].series)} />
          </Field>
        </div>
      </Section>

      <Section title="Cache & Aktualisierung">
        <div className="form-grid">
          <Field label="Cache-Dauer (Stunden)" help="Antworten der Provider werden so lange zwischengespeichert">
            <NumberInput value={d.cache_hours} onValue={(v) => set("cache_hours", v)} min={0} />
          </Field>
          <Field label="Aktualisierungsintervall (Stunden)" help="Automatischer Metadaten-Refresh der Bibliothek (0 = aus)">
            <NumberInput value={d.refresh_interval_hours} onValue={(v) => set("refresh_interval_hours", v)} min={0} />
          </Field>
        </div>
      </Section>
      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={async () => {
          if (await save()) qc.invalidateQueries({ queryKey: ["metadata-providers"] });
        }}
        onReset={reset}
      />
    </div>
  );
}
