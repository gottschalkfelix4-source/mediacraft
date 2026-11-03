// Activity.
import type { Episode, LookupIds, Movie } from "./media";
import type { ParsedRelease } from "./releases";
import type { RootMediaType } from "./config";

export interface DelayProfile {
  id: number;
  order: number;
  enabled: boolean;
  preferred_protocol: "usenet" | "torrent";
  usenet_delay: number;
  torrent_delay: number;
  bypass_highest_quality: boolean;
  bypass_min_score: number | null;
  tags: number[];
}

export interface PendingRelease {
  id: number;
  title: string;
  media_type: "movie" | "series";
  movie_id: number | null;
  series_id: number | null;
  episode_ids: number[];
  target: string;
  protocol: string;
  quality: string;
  format_score: number;
  indexer: string | null;
  size: number;
  added: string | null;
  release_at: string | null;
  reason: string | null;
}

export interface QualityDefinition {
  name: string;
  source: string;
  resolution: number;
  rank: number;
  min: number;
  max: number;
  default_min: number;
  default_max: number;
  custom: boolean;
}

export interface RecycleEntry {
  path: string;
  original: string | null;
  deleted: string | null;
  size: number;
  folder: boolean;
}

export interface RecycleListing {
  folder: string | null;
  days: number;
  entries: RecycleEntry[];
}

export interface ImportListField {
  key: string;
  label: string;
  help: string;
}

export interface ImportListSchema {
  kind: string;
  label: string;
  media: ("movie" | "series")[];
  fields: ImportListField[];
}

export interface ImportList {
  id: number;
  name: string;
  kind: string;
  enabled: boolean;
  media_type: "movie" | "series";
  settings: Record<string, string>;
  quality_profile_id: number;
  root_folder: string;
  monitored: boolean;
  monitor: string;
  minimum_availability: string;
  series_type: string;
  search_on_add: boolean;
  tags: number[];
  last_sync: string | null;
  last_error: string | null;
  last_result: { items?: number; added?: number; existing?: number; excluded?: number; failed?: number };
}

export interface ImportListTest {
  items: number;
  new: string[];
  new_count: number;
  existing: number;
  excluded: number;
}

export interface ImportListExclusion {
  id: number;
  media_type: "movie" | "series";
  tmdb_id: number | null;
  tvdb_id: number | null;
  imdb_id: string | null;
  title: string;
  year: number | null;
  added: string | null;
}

export interface CollectionPart {
  media_type: "movie";
  ids: { tmdb: number };
  title: string;
  year: number | null;
  overview: string | null;
  images: { poster?: string | null };
  movie_id: number | null;
  has_file: boolean;
  monitored: boolean;
  excluded: boolean;
}

export interface MovieCollection {
  id: number;
  name: string;
  overview: string | null;
  images: { poster?: string | null; fanart?: string | null };
  parts: CollectionPart[];
  in_library: number;
  missing: number;
  watch_list_id: number | null;
}

export interface StatsBucket {
  name: string;
  count: number;
  size: number;
}

export interface StatsData {
  library: {
    movies: number;
    movies_with_file: number;
    series: number;
    episodes: number;
    episodes_with_file: number;
    movie_size: number;
    episode_size: number;
    total_size: number;
    files: number;
  };
  qualities: StatsBucket[];
  languages: StatsBucket[];
  codecs: StatsBucket[];
  resolutions: StatsBucket[];
  release_groups: StatsBucket[];
  root_folders: { path: string; media_type: string; library_size: number; total: number | null; free: number | null }[];
  weeks: { week: string; grabs: number; imports: number; failed: number }[];
  indexers: { name: string; grabs: number; queries: number; failed: number }[];
}

export interface BulkEdit {
  ids: number[];
  changes: Record<string, unknown>;
  tags_mode?: "add" | "remove" | "replace";
  move_files?: boolean;
}

export interface BulkResult {
  updated: number;
  errors: string[];
}

export interface QueueItem {
  id: number;
  title: string;
  status: string;
  client_status: string | null;
  protocol: string;
  download_id: string;
  download_client_id: number;
  download_client: string | null;
  indexer: string | null;
  quality: string;
  languages: string[];
  format_score: number;
  size: number;
  size_left: number;
  progress: number;
  eta_seconds: number | null;
  output_path: string | null;
  messages: string[];
  media_type: string;
  movie_id: number | null;
  series_id: number | null;
  episode_ids: number[];
  target: { type: "movie" | "series"; id: number; title: string; year?: number | null } | null;
  added: string | null;
  updated: string | null;
  manual: boolean;
  import_progress: number | null; // % while files are copied into the library
  stalled_since: string | null; // no progress since (stall timeout)
}

export interface HistoryRecord {
  id: number;
  event: string;
  date: string | null;
  media_type: string;
  movie_id: number | null;
  series_id: number | null;
  episode_ids: number[];
  source_title: string;
  quality: string | null;
  indexer: string | null;
  download_client: string | null;
  download_id: string | null;
  data: Record<string, unknown> | null;
  title?: string | null;
}

export interface HistoryPage {
  total: number;
  page: number;
  page_size: number;
  records: HistoryRecord[];
}

export interface BlocklistItem {
  id: number;
  date: string | null;
  media_type: string;
  movie_id: number | null;
  series_id: number | null;
  source_title: string;
  indexer: string | null;
  protocol: string | null;
  reason: string | null;
}

export interface CalendarItem {
  type: "episode" | "movie";
  id: number;
  series_id?: number;
  title: string;
  season?: number;
  number?: number;
  absolute_number?: number | null;
  episode_title?: string | null;
  year?: number | null;
  release_type?: "cinema" | "digital" | "physical";
  date: string | null;
  has_file: boolean;
  monitored: boolean;
  network?: string | null;
  poster?: string | null;
}

export interface Dashboard {
  movies: { total: number; with_file: number; missing: number };
  series: { total: number; episodes: number; episode_files: number; missing: number };
  size_on_disk: number;
  queue: number;
  upcoming: CalendarItem[];
  recent: HistoryRecord[];
}

export interface WantedResult {
  movies: Movie[];
  episodes: Episode[];
}

export interface RenamePreview {
  file_id: number;
  existing: string;
  new: string;
}

export interface UnmappedFolder {
  folder: string;
  path: string;
  title: string;
  year: number | null;
  ids: LookupIds;
  media_type: RootMediaType;
}

export interface ManualImportItem {
  path: string;
  size: number;
  parsed: ParsedRelease;
  quality: string;
  languages: string[];
  movie_id: number | null;
  series_id: number | null;
  episode_ids: number[];
  rejections: string[];
}

export interface ManualImportResult {
  path: string;
  ok: boolean;
  error?: string;
}

export interface SSEMessage {
  type: string;
  data: Record<string, unknown>;
  ts: string;
}
