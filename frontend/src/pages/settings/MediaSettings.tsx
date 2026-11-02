import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Trash2, HardDrive, AlertTriangle, FolderSearch } from "lucide-react";
import { api } from "../../api";
import { Badge, ErrorBox, Field, Loading, NumberInput, Select, TextInput, Toggle, Empty } from "../../components/ui";
import { FileBrowser } from "../../components/FileBrowser";
import { useConfirm } from "../../components/Modal";
import { useApiMutation, useRootFolders } from "../../hooks";
import { fmtSize } from "../../format";
import { SaveBar, Section, useSection } from "./common";
import type { MediaSettings as MS, RootMediaType } from "../../types";

const MOVIE_TOKENS = ["{Movie Title}", "{Movie TitleThe}", "{Movie CleanTitle}", "{Movie OriginalTitle}", "{Release Year}", "{ImdbId}", "{TmdbId}", "{Movie Collection}", "{Movie Certification}"];
const SERIES_TOKENS = ["{Series Title}", "{Series TitleThe}", "{Series CleanTitle}", "{Series Year}", "{TvdbId}", "{TmdbId}", "{ImdbId}", "{Network}"];
const EPISODE_TOKENS = ["{season:00}", "{episode:00}", "{absolute:000}", "{Episode Title}", "{Air-Date}", "{Air Date}"];
const FILE_TOKENS = ["{Quality Full}", "{Quality Title}", "{Release Group}", "{-Release Group}", "{Edition Tags}", "{[Edition Tags]}", "{MediaInfo VideoCodec}", "{MediaInfo VideoDynamicRange}", "{MediaInfo VideoDynamicRangeType}", "{MediaInfo AudioCodec}", "{MediaInfo AudioChannels}", "{Languages}", "{Original Title}"];

function TokenHelp({ groups, onInsert }: { groups: [string, string[]][]; onInsert: (t: string) => void }) {
  return (
    <div className="token-help">
      {groups.map(([label, tokens]) => (
        <div key={label} className="token-group">
          <span className="token-group-label">{label}</span>
          {tokens.map((t) => (
            <button type="button" key={t} className="token" onClick={() => onInsert(t)} title="Einfügen">
              {t}
            </button>
          ))}
        </div>
      ))}
      <div className="muted small">
        Zeichen innerhalb der Klammern vor/nach dem Namen erscheinen nur, wenn der Wert nicht leer ist: <code>{"{-Release Group}"}</code> → „-GROUP“ oder nichts. Zahlen-Tokens mit Pad-Format: <code>{"{season:00}"}</code>.
      </div>
    </div>
  );
}

function TemplateField({ label, value, onChange, groups, focusKey, focused, setFocused }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  groups: [string, string[]][];
  focusKey: string;
  focused: string | null;
  setFocused: (k: string | null) => void;
}) {
  return (
    <Field label={label}>
      <TextInput value={value} onValue={onChange} className="mono" onFocus={() => setFocused(focusKey)} />
      {focused === focusKey && <TokenHelp groups={groups} onInsert={(t) => onChange(value + t)} />}
    </Field>
  );
}

export function MediaSettings() {
  const { draft, set, save, reset, dirty, saving, isLoading, error } = useSection("media");
  const [focused, setFocused] = useState<string | null>(null);
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !draft) return <Loading />;
  const d = draft as MS;

  return (
    <div className="settings-page">
      <RootFolders />

      <Section title="Umbenennen & Benennung" help="Klick in ein Feld zeigt die verfügbaren Tokens.">
        <Toggle checked={d.rename} onChange={(v) => set("rename", v)} label="Dateien beim Import umbenennen" />
        <div className="form-grid mt">
          <TemplateField label="Film-Ordner" value={d.movie_folder} onChange={(v) => set("movie_folder", v)} groups={[["Film", MOVIE_TOKENS]]} focusKey="mf" focused={focused} setFocused={setFocused} />
          <TemplateField label="Film-Datei" value={d.movie_file} onChange={(v) => set("movie_file", v)} groups={[["Film", MOVIE_TOKENS], ["Datei", FILE_TOKENS]]} focusKey="mfile" focused={focused} setFocused={setFocused} />
          <TemplateField label="Serien-Ordner" value={d.series_folder} onChange={(v) => set("series_folder", v)} groups={[["Serie", SERIES_TOKENS]]} focusKey="sf" focused={focused} setFocused={setFocused} />
          <TemplateField label="Staffel-Ordner" value={d.season_folder} onChange={(v) => set("season_folder", v)} groups={[["Episode", ["{season:00}", "{season:0}"]]]} focusKey="seaf" focused={focused} setFocused={setFocused} />
          <Field label="Specials-Ordner">
            <TextInput value={d.specials_folder} onValue={(v) => set("specials_folder", v)} className="mono" />
          </Field>
          <TemplateField label="Episoden-Datei (Standard)" value={d.episode_file} onChange={(v) => set("episode_file", v)} groups={[["Serie", SERIES_TOKENS], ["Episode", EPISODE_TOKENS], ["Datei", FILE_TOKENS]]} focusKey="ef" focused={focused} setFocused={setFocused} />
          <TemplateField label="Episoden-Datei (Täglich)" value={d.daily_file} onChange={(v) => set("daily_file", v)} groups={[["Serie", SERIES_TOKENS], ["Episode", EPISODE_TOKENS], ["Datei", FILE_TOKENS]]} focusKey="df" focused={focused} setFocused={setFocused} />
          <TemplateField label="Episoden-Datei (Anime)" value={d.anime_file} onChange={(v) => set("anime_file", v)} groups={[["Serie", SERIES_TOKENS], ["Episode", EPISODE_TOKENS], ["Datei", FILE_TOKENS]]} focusKey="af" focused={focused} setFocused={setFocused} />
          <Field label="Mehrfach-Episoden">
            <Select
              value={d.multi_episode_style}
              onValue={(v) => set("multi_episode_style", v)}
              options={[
                { value: "extend", label: "Erweitern (S01E01-E02)" },
                { value: "duplicate", label: "Duplizieren (S01E01E02)" },
              ]}
            />
          </Field>
          <Field label="Doppelpunkt ersetzen durch">
            <TextInput value={d.colon_replacement} onValue={(v) => set("colon_replacement", v)} className="mono" />
          </Field>
        </div>
      </Section>

      <Section title="Dateiverwaltung">
        <div className="col gap-sm mb">
          <Toggle checked={d.use_hardlinks} onChange={(v) => set("use_hardlinks", v)} label="Hardlinks statt Kopieren verwenden (wenn möglich)" />
          <Toggle checked={d.upgrade_propers} onChange={(v) => set("upgrade_propers", v)} label="Propers/Repacks als Upgrade behandeln" />
          <Toggle checked={d.delete_empty_folders} onChange={(v) => set("delete_empty_folders", v)} label="Leere Ordner löschen" />
          <Toggle checked={d.import_extra_files} onChange={(v) => set("import_extra_files", v)} label="Zusatzdateien importieren (Untertitel, NFO …)" />
        </div>
        <div className="form-grid">
          <Field label="Zusatzdatei-Endungen" help="Kommagetrennt">
            <TextInput value={d.extra_extensions} onValue={(v) => set("extra_extensions", v)} className="mono" disabled={!d.import_extra_files} />
          </Field>
          <Field label="Papierkorb-Ordner" help="Leer = Dateien direkt löschen">
            <TextInput value={d.recycle_bin} onValue={(v) => set("recycle_bin", v)} className="mono" placeholder="/data/.recycle" />
          </Field>
          <Field label="Papierkorb leeren nach (Tagen)">
            <NumberInput value={d.recycle_bin_days} onValue={(v) => set("recycle_bin_days", v)} min={0} />
          </Field>
          <Field label="Sample-Grenze (MB)" help="Kleinere Videodateien gelten als Sample">
            <NumberInput value={d.sample_max_mb} onValue={(v) => set("sample_max_mb", v)} min={0} />
          </Field>
          <Field label="Mindestens frei (MB)" help="Import abbrechen, wenn weniger frei">
            <NumberInput value={d.min_free_space_mb} onValue={(v) => set("min_free_space_mb", v)} min={0} />
          </Field>
          <Field label="Datei-chmod" help="z. B. 664 (leer = unverändert, nur Linux)">
            <TextInput value={d.file_chmod} onValue={(v) => set("file_chmod", v)} className="mono" />
          </Field>
        </div>
      </Section>
      <SaveBar dirty={dirty} saving={saving} onSave={() => save()} onReset={reset} />
    </div>
  );
}

function RootFolders() {
  const { data, isLoading, error } = useRootFolders();
  const [browse, setBrowse] = useState(false);
  const [type, setType] = useState<RootMediaType>("movie");
  const confirm = useConfirm();
  const qc = useQueryClient();
  const add = useApiMutation((p: { path: string; type: RootMediaType }) => api.addRootFolder(p.path, p.type), {
    invalidate: [["rootfolders"], ["health"], ["diskspace"]],
    success: "Root-Folder hinzugefügt",
  });
  const del = useApiMutation((id: number) => api.deleteRootFolder(id), { invalidate: [["rootfolders"], ["diskspace"]], success: "Root-Folder entfernt" });
  const label = { movie: "Filme", series: "Serien", anime: "Anime" };

  return (
    <Section
      title="Root-Folder"
      help="Basisordner, in denen Filme und Serien abgelegt werden."
      actions={
        <div className="row gap-sm">
          <Select<RootMediaType>
            value={type}
            onValue={setType}
            aria-label="Medientyp"
            options={[
              { value: "movie", label: "Filme" },
              { value: "series", label: "Serien" },
              { value: "anime", label: "Anime" },
            ]}
          />
          <button className="btn btn-primary" onClick={() => setBrowse(true)}>
            <FolderPlus size={15} /> Hinzufügen
          </button>
        </div>
      }
    >
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && <Empty icon={<FolderSearch size={32} />} title="Noch kein Root-Folder" />}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Pfad</th>
                <th>Typ</th>
                <th className="num">Frei</th>
                <th className="num">Gesamt</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td className="mono">
                    {r.accessible ? <HardDrive size={14} className="muted" /> : <AlertTriangle size={14} className="tone-text-danger" />} {r.path}
                  </td>
                  <td>
                    <Badge tone={r.media_type === "movie" ? "info" : r.media_type === "anime" ? "accent" : "success"}>{label[r.media_type] ?? r.media_type}</Badge>
                  </td>
                  <td className="num">{r.accessible ? fmtSize(r.free_space) : <span className="tone-text-danger">nicht erreichbar</span>}</td>
                  <td className="num">{fmtSize(r.total_space)}</td>
                  <td className="actions">
                    <button
                      className="icon-btn danger"
                      title="Entfernen"
                      aria-label="Root-Folder entfernen"
                      onClick={async () => {
                        if (await confirm({ title: "Root-Folder entfernen?", message: <>„{r.path}“ wird aus der Konfiguration entfernt. Dateien bleiben erhalten.</>, confirmLabel: "Entfernen", danger: true })) del.mutate(r.id);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {browse && (
        <FileBrowser
          title={`Root-Folder für ${label[type]} wählen`}
          onClose={() => setBrowse(false)}
          onSelect={(p) => {
            setBrowse(false);
            add.mutate({ path: p, type });
            qc.invalidateQueries({ queryKey: ["rootfolders"] });
          }}
        />
      )}
    </Section>
  );
}
