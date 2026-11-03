// Formatting helpers: German dates (local time), sizes, durations.

/** Parse a backend timestamp. Strings without zone are treated as UTC. */
export function parseDate(v: string | null | undefined): Date | null {
  if (!v) return null;
  let s = v.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    // plain date: interpret as local calendar date
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  s = s.replace(" ", "T");
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
  // Python may emit microseconds (6 digits) – trim to milliseconds
  s = s.replace(/(\.\d{3})\d+/, "$1");
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

const pad = (n: number) => String(n).padStart(2, "0");

export function fmtDate(v: string | Date | null | undefined): string {
  const d = v instanceof Date ? v : parseDate(v);
  if (!d) return "–";
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

export function fmtTime(v: string | Date | null | undefined): string {
  const d = v instanceof Date ? v : parseDate(v);
  if (!d) return "–";
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtDateTime(v: string | Date | null | undefined): string {
  const d = v instanceof Date ? v : parseDate(v);
  if (!d) return "–";
  return `${fmtDate(d)} ${fmtTime(d)}`;
}

export const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
export const WEEKDAYS_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
export const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

/** "in 3 h 12 min" / "vor 5 min" */
export function relTime(v: string | Date | null | undefined, now: Date = new Date()): string {
  const d = v instanceof Date ? v : parseDate(v);
  if (!d) return "–";
  const diff = d.getTime() - now.getTime();
  const txt = fmtDuration(Math.abs(diff) / 1000);
  if (Math.abs(diff) < 30_000) return "jetzt";
  return diff > 0 ? `in ${txt}` : `vor ${txt}`;
}

/** 3 d 4 h / 3 h 12 min / 4 min / 12 s */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !isFinite(seconds)) return "–";
  const s = Math.round(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return h ? `${d} d ${h} h` : `${d} d`;
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
}

export function fmtSize(bytes: number | null | undefined, digits = 1): string {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return "–";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toLocaleString("de-DE", { maximumFractionDigits: i < 2 ? 0 : digits, minimumFractionDigits: 0 })} ${units[i]}`;
}

export function fmtAge(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "–";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} d`;
}

export function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return n.toLocaleString("de-DE");
}

export function epCode(season: number | undefined, number: number | undefined): string {
  if (season === undefined || number === undefined) return "";
  return `S${pad(season)}E${pad(number)}`;
}

export function isoLocalDay(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ISO string in UTC without zone suffix (backend calendar expects naive UTC). */
export function toUtcNaive(d: Date): string {
  return d.toISOString().slice(0, 19);
}

export const LANGUAGE_LABELS: Record<string, string> = {
  german: "Deutsch",
  english: "Englisch",
  french: "Französisch",
  spanish: "Spanisch",
  italian: "Italienisch",
  dutch: "Niederländisch",
  japanese: "Japanisch",
  korean: "Koreanisch",
  chinese: "Chinesisch",
  russian: "Russisch",
  polish: "Polnisch",
  portuguese: "Portugiesisch",
  swedish: "Schwedisch",
  danish: "Dänisch",
  norwegian: "Norwegisch",
  finnish: "Finnisch",
  turkish: "Türkisch",
  hindi: "Hindi",
  czech: "Tschechisch",
  hungarian: "Ungarisch",
  multi: "Multi",
  original: "Originalsprache",
};
export const LANGUAGES = Object.keys(LANGUAGE_LABELS);

export function langLabel(l: string): string {
  return LANGUAGE_LABELS[l] ?? l;
}

export const AVAILABILITY_LABELS: Record<string, string> = {
  announced: "Angekündigt",
  in_cinemas: "Im Kino",
  released: "Veröffentlicht",
};

export const MOVIE_STATUS_LABELS: Record<string, string> = {
  announced: "Angekündigt",
  in_cinemas: "Im Kino",
  released: "Veröffentlicht",
};

export const SERIES_STATUS_LABELS: Record<string, string> = {
  continuing: "Laufend",
  ended: "Beendet",
  upcoming: "Demnächst",
};

export const SERIES_TYPE_LABELS: Record<string, string> = {
  standard: "Standard",
  daily: "Täglich",
  anime: "Anime",
};

export const MONITOR_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "Alle Episoden" },
  { value: "future", label: "Zukünftige Episoden" },
  { value: "missing", label: "Fehlende Episoden" },
  { value: "existing", label: "Vorhandene Episoden" },
  { value: "first_season", label: "Erste Staffel" },
  { value: "latest_season", label: "Neueste Staffel" },
  { value: "pilot", label: "Nur Pilotfolge" },
  { value: "none", label: "Keine" },
];

export const PROVIDER_LABELS: Record<string, string> = {
  tmdb: "TMDB",
  tvdb: "TheTVDB",
  tvmaze: "TVmaze",
  omdb: "OMDb",
  anilist: "AniList",
};

export const HISTORY_EVENT_LABELS: Record<string, string> = {
  grabbed: "Geladen",
  imported: "Importiert",
  upgraded: "Upgrade",
  failed: "Fehlgeschlagen",
  deleted: "Gelöscht",
  renamed: "Umbenannt",
  ignored: "Ignoriert",
};

export const QUEUE_STATUS_LABELS: Record<string, string> = {
  grabbed: "Gesendet",
  queued: "Wartend",
  downloading: "Lädt",
  paused: "Pausiert",
  completed: "Fertig",
  importing: "Importiert…",
  imported: "Importiert",
  failed: "Fehlgeschlagen",
  import_blocked: "Import blockiert",
  warning: "Warnung",
  removed: "Entfernt",
};

export const COMMAND_LABELS: Record<string, string> = {
  movie_search: "Filmsuche",
  movies_search: "Filmsuche (mehrere)",
  episode_search: "Episodensuche",
  season_search: "Staffelsuche",
  series_search: "Seriensuche",
  refresh_movie: "Film aktualisieren",
  refresh_series: "Serie aktualisieren",
  refresh_all: "Metadaten aktualisieren",
  rename_movie: "Film umbenennen",
  rename_series: "Serie umbenennen",
  rss_sync: "RSS-Sync",
  wanted_search: "Fehlende suchen",
  cutoff_search: "Cutoff-Suche",
  check_downloads: "Downloads prüfen",
  health_check: "Health-Check",
  disk_scan_all: "Festplatten-Scan",
  housekeeping: "Aufräumen",
  backup: "Backup",
  process_pending: "Zurückgestellte Releases",
};

export function commandLabel(name: string): string {
  if (name.startsWith("task:")) return `Aufgabe: ${COMMAND_LABELS[name.slice(5)] ?? name.slice(5)}`;
  return COMMAND_LABELS[name] ?? name;
}

export function providerLabel(p: string): string {
  return PROVIDER_LABELS[p] ?? p;
}

export function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}
