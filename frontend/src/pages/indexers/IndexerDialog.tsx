import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PlugZap, Save, Eye, EyeOff } from "lucide-react";
import { api, errorMessage } from "../../api";
import { ChipInput, Field, NumberInput, Select, Spinner, TextInput, Toggle } from "../../components/ui";
import { Modal } from "../../components/Modal";
import { TagSelect } from "../../components/TagSelect";
import { useToast } from "../../components/Toast";
import { windowLabel } from "../../components/Usage";
import type { Indexer, IndexerBase } from "../../types";

const CATEGORY_NAMES: Record<number, string> = {
  2000: "Filme", 2010: "Filme/Fremdspr.", 2020: "Filme/Sonstige", 2030: "Filme/SD", 2040: "Filme/HD", 2045: "Filme/UHD", 2050: "Filme/BluRay", 2060: "Filme/3D",
  5000: "TV", 5010: "TV/WEB-DL", 5020: "TV/Fremdspr.", 5030: "TV/SD", 5040: "TV/HD", 5045: "TV/UHD", 5050: "TV/Sonstige", 5070: "TV/Anime",
};

const DEFAULTS: IndexerBase = {
  name: "",
  kind: "newznab",
  url: "",
  api_path: "/api",
  api_key: "",
  movie_categories: [2000],
  tv_categories: [5000],
  anime_categories: [5070],
  additional_params: "",
  enabled: true,
  enable_rss: true,
  enable_auto_search: true,
  enable_interactive_search: true,
  priority: 25,
  minimum_seeders: 1,
  seed_ratio: null,
  seed_time: null,
  download_client_id: null,
  tags: [],
  query_limit: 0,
  grab_limit: 0,
  limit_window_hours: 24,
  limit_mode: "rolling",
  limit_reset_hour: 0,
  grab_reserve: 0,
  query_reserve: 0,
  min_request_interval: 0,
  sync_remote_limits: true,
};

function pick(i: Indexer): IndexerBase {
  const out = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS) as (keyof IndexerBase)[]) {
    if (i[k] !== undefined) (out as Record<string, unknown>)[k] = i[k] ?? DEFAULTS[k];
  }
  out.seed_ratio = i.seed_ratio;
  out.seed_time = i.seed_time;
  out.download_client_id = i.download_client_id;
  return out;
}

function CategoryPicker({ label, value, onChange, presets }: { label: string; value: number[]; onChange: (v: number[]) => void; presets: number[] }) {
  return (
    <Field label={label}>
      <div className="chips">
        {presets.map((c) => {
          const on = value.includes(c);
          return (
            <button type="button" key={c} className={`chip ${on ? "chip-active" : ""}`} onClick={() => onChange(on ? value.filter((x) => x !== c) : [...value, c].sort((a, b) => a - b))} title={CATEGORY_NAMES[c] ?? String(c)} aria-pressed={on}>
              {c} <span className="chip-sub">{CATEGORY_NAMES[c] ?? ""}</span>
            </button>
          );
        })}
      </div>
      <ChipInput values={value.filter((v) => !presets.includes(v))} numeric placeholder="Weitere Kategorie-ID + Enter" onChange={(extra) => onChange([...value.filter((v) => presets.includes(v)), ...(extra as number[])].sort((a, b) => a - b))} />
    </Field>
  );
}

export function IndexerDialog({ indexer, onClose }: { indexer: Indexer | null; onClose: () => void }) {
  const [f, setF] = useState<IndexerBase>(() => (indexer ? pick(indexer) : { ...DEFAULTS }));
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const presets = useQuery({ queryKey: ["indexer-presets"], queryFn: api.indexerPresets, staleTime: Infinity });
  const clients = useQuery({ queryKey: ["downloadclients"], queryFn: api.downloadClients });
  const qc = useQueryClient();
  const toast = useToast();
  const set = <K extends keyof IndexerBase>(k: K, v: IndexerBase[K]) => setF((o) => ({ ...o, [k]: v }));

  const cats = presets.data?.categories ?? { movie: [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060], tv: [5000, 5010, 5020, 5030, 5040, 5045, 5050], anime: [5070] };
  const protocol = f.kind === "torznab" ? "torrent" : "usenet";

  const applyPreset = (name: string) => {
    const p = presets.data?.limits.find((x) => x.name === name);
    if (!p) return;
    setF((o) => ({
      ...o,
      query_limit: p.query_limit,
      grab_limit: p.grab_limit,
      limit_window_hours: p.limit_window_hours,
      limit_mode: p.limit_mode,
      limit_reset_hour: p.limit_reset_hour ?? o.limit_reset_hour,
    }));
  };
  const currentPreset =
    presets.data?.limits.find(
      (p) => p.query_limit === f.query_limit && p.grab_limit === f.grab_limit && p.limit_window_hours === f.limit_window_hours && p.limit_mode === f.limit_mode && (p.limit_mode !== "fixed" || (p.limit_reset_hour ?? 0) === f.limit_reset_hour),
    )?.name ?? "";

  const save = async () => {
    if (!f.name.trim() || !f.url.trim()) {
      toast.error("Name und URL sind erforderlich");
      return;
    }
    setBusy(true);
    try {
      if (indexer) await api.updateIndexer(indexer.id, f);
      else await api.createIndexer(f);
      toast.success(indexer ? "Indexer gespeichert" : "Indexer angelegt", f.name);
      qc.invalidateQueries({ queryKey: ["indexers"] });
      qc.invalidateQueries({ queryKey: ["indexers-usage"] });
      qc.invalidateQueries({ queryKey: ["indexer-usage"] });
      onClose();
    } catch (e) {
      toast.error("Speichern fehlgeschlagen", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      const r = await api.testIndexer(f);
      const caps = r.capabilities ?? {};
      const searching = (caps as Record<string, unknown>).searching ?? (caps as Record<string, unknown>).search;
      toast.success("Test erfolgreich", searching ? `Unterstützte Suchen: ${Object.keys(searching as object).join(", ")}` : "Capabilities abgerufen");
    } catch (e) {
      toast.error("Test fehlgeschlagen", errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal
      title={indexer ? `Indexer bearbeiten: ${indexer.name}` : "Indexer hinzufügen"}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn mr-auto" onClick={test} disabled={testing || !f.url}>
            {testing ? <Spinner size={14} /> : <PlugZap size={15} />} Testen
          </button>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? <Spinner size={14} /> : <Save size={15} />} Speichern
          </button>
        </>
      }
    >
      <div className="form-section">
        <h4>Verbindung</h4>
        <div className="form-grid">
          <Field label="Name">
            <TextInput value={f.name} onValue={(v) => set("name", v)} placeholder="z. B. TreasureMaps" />
          </Field>
          <Field label="Typ">
            <Select
              value={f.kind}
              onValue={(v) => set("kind", v)}
              options={[
                { value: "newznab", label: "Newznab (Usenet)" },
                { value: "torznab", label: "Torznab (Torrent)" },
              ]}
            />
          </Field>
          <Field label="URL">
            <TextInput value={f.url} onValue={(v) => set("url", v)} placeholder="https://indexer.example" className="mono" />
          </Field>
          <Field label="API-Pfad">
            <TextInput value={f.api_path} onValue={(v) => set("api_path", v)} placeholder="/api" className="mono" />
          </Field>
          <Field label="API-Key">
            <div className="row gap-sm">
              <input className="input mono grow" type={showKey ? "text" : "password"} autoComplete="off" value={f.api_key} onChange={(e) => set("api_key", e.target.value)} />
              <button type="button" className="icon-btn" onClick={() => setShowKey(!showKey)} title={showKey ? "Verbergen" : "Anzeigen"} aria-label="API-Key anzeigen">
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </Field>
          <Field label="Zusätzliche Parameter" help="z. B. &extended=1">
            <TextInput value={f.additional_params} onValue={(v) => set("additional_params", v)} className="mono" />
          </Field>
        </div>
      </div>

      <div className="form-section">
        <h4>Kategorien</h4>
        <CategoryPicker label="Filme" value={f.movie_categories} onChange={(v) => set("movie_categories", v)} presets={cats.movie} />
        <CategoryPicker label="Serien" value={f.tv_categories} onChange={(v) => set("tv_categories", v)} presets={cats.tv} />
        <CategoryPicker label="Anime" value={f.anime_categories} onChange={(v) => set("anime_categories", v)} presets={cats.anime} />
      </div>

      <div className="form-section">
        <h4>Verwendung</h4>
        <div className="row gap wrap mb">
          <Toggle checked={f.enabled} onChange={(v) => set("enabled", v)} label="Aktiv" />
          <Toggle checked={f.enable_rss} onChange={(v) => set("enable_rss", v)} label="RSS" />
          <Toggle checked={f.enable_auto_search} onChange={(v) => set("enable_auto_search", v)} label="Automatische Suche" />
          <Toggle checked={f.enable_interactive_search} onChange={(v) => set("enable_interactive_search", v)} label="Interaktive Suche" />
        </div>
        <div className="form-grid">
          <Field label="Priorität" help="1–50, kleiner = bevorzugt">
            <NumberInput value={f.priority} onValue={(v) => set("priority", v)} min={1} max={50} />
          </Field>
          <Field label="Downloadclient" help="Optional fester Client für diesen Indexer">
            <Select
              value={f.download_client_id ?? 0}
              onValue={(v) => set("download_client_id", v || null)}
              options={[{ value: 0, label: "Automatisch" }, ...(clients.data ?? []).filter((c) => c.protocol === protocol).map((c) => ({ value: c.id, label: c.name }))]}
            />
          </Field>
          {protocol === "torrent" && (
            <>
              <Field label="Mindest-Seeder">
                <NumberInput value={f.minimum_seeders} onValue={(v) => set("minimum_seeders", v)} min={0} />
              </Field>
              <Field label="Seed-Ratio" help="leer = Client-Standard">
                <input className="input input-num" type="number" step="0.1" min={0} value={f.seed_ratio ?? ""} onChange={(e) => set("seed_ratio", e.target.value === "" ? null : Number(e.target.value))} />
              </Field>
              <Field label="Seed-Zeit (min)" help="leer = Client-Standard">
                <input className="input input-num" type="number" min={0} value={f.seed_time ?? ""} onChange={(e) => set("seed_time", e.target.value === "" ? null : Number(e.target.value))} />
              </Field>
            </>
          )}
        </div>
        <Field label="Tags" help="Nur für Filme/Serien mit mindestens einem dieser Tags verwenden (leer = alle)">
          <TagSelect value={f.tags} onChange={(v) => set("tags", v)} />
        </Field>
      </div>

      <div className="form-section limits-section">
        <h4>Limits &amp; Kontingente</h4>
        <Field label="Vorlage">
          <Select value={currentPreset} onValue={applyPreset} options={[{ value: "", label: "Benutzerdefiniert" }, ...(presets.data?.limits ?? []).map((p) => ({ value: p.name, label: p.name }))]} />
        </Field>
        <div className="form-grid">
          <Field label="Query-Limit" help="API-Anfragen pro Fenster (0 = unbegrenzt)">
            <NumberInput value={f.query_limit} onValue={(v) => set("query_limit", v)} min={0} />
          </Field>
          <Field label="Grab-Limit" help="NZB-/Torrent-Downloads pro Fenster (0 = unbegrenzt)">
            <NumberInput value={f.grab_limit} onValue={(v) => set("grab_limit", v)} min={0} />
          </Field>
          <Field label="Fenster (Stunden)">
            <NumberInput value={f.limit_window_hours} onValue={(v) => set("limit_window_hours", v)} min={1} step={1} />
          </Field>
          <Field label="Modus">
            <Select
              value={f.limit_mode}
              onValue={(v) => set("limit_mode", v)}
              options={[
                { value: "rolling", label: "Rollierend (ältester Eintrag fällt heraus)" },
                { value: "fixed", label: "Fester Reset-Zeitpunkt" },
              ]}
            />
          </Field>
          {f.limit_mode === "fixed" && (
            <Field label="Reset-Stunde (UTC)" help={`= ${String((f.limit_reset_hour + Math.round(-new Date().getTimezoneOffset() / 60) + 24) % 24).padStart(2, "0")}:00 Uhr lokal`}>
              <NumberInput value={f.limit_reset_hour} onValue={(v) => set("limit_reset_hour", Math.max(0, Math.min(23, v)))} min={0} max={23} />
            </Field>
          )}
          <Field label="Grab-Reserve" help="Letzte Grabs nur für manuelle (interaktive) Aktionen">
            <NumberInput value={f.grab_reserve} onValue={(v) => set("grab_reserve", v)} min={0} />
          </Field>
          <Field label="Query-Reserve" help="Letzte Queries nur für manuelle Suchen">
            <NumberInput value={f.query_reserve} onValue={(v) => set("query_reserve", v)} min={0} />
          </Field>
          <Field label="Mindestabstand (s)" help="Pause zwischen zwei Anfragen">
            <NumberInput value={f.min_request_interval} onValue={(v) => set("min_request_interval", v)} min={0} step={0.5} />
          </Field>
        </div>
        <Toggle checked={f.sync_remote_limits} onChange={(v) => set("sync_remote_limits", v)} label="Zähler/Limits vom Indexer übernehmen (newznab:apilimits)" />
        <div className="limit-summary">
          {f.query_limit || f.grab_limit ? (
            <>
              {f.query_limit ? `${f.query_limit} Queries` : "Queries unbegrenzt"} · {f.grab_limit ? `${f.grab_limit} Grabs` : "Grabs unbegrenzt"} –{" "}
              {windowLabel(f.limit_mode, f.limit_window_hours, f.limit_reset_hour)}
              {f.grab_reserve > 0 && ` · ${f.grab_reserve} Grabs Reserve`}
            </>
          ) : (
            "Keine Limits – nur Zählung"
          )}
        </div>
      </div>
    </Modal>
  );
}
