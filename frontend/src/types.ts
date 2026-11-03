// TypeScript mirrors of the MediaCraft backend response shapes (see backend/app).

export type ID = number;

export interface AuthStatus {
  method: "none" | "forms";
  authenticated: boolean;
  app: string;
  version: string;
}

export interface Images {
  poster?: string | null;
  fanart?: string | null;
  banner?: string | null;
  [k: string]: string | null | undefined;
}

export interface Rating {
  value?: number | null;
  votes?: number | null;
}

export interface MediaFile {
  id: number;
  media_type: string;
  path: string;
  size: number;
  quality: string;
  proper: number;
  languages: string[];
  release_group: string | null;
  release_name: string | null;
  format_score: number;
  edition: string | null;
  media_info: Record<string, unknown>;
  added: string | null;
}

export type MinimumAvailability = "announced" | "in_cinemas" | "released";

export interface Movie {
  id: number;
  type: "movie";
  tmdb_id: number | null;
  imdb_id: string | null;
  anilist_id: number | null;
  title: string;
  original_title: string | null;
  sort_title: string;
  alt_titles: string[];
  year: number | null;
  overview: string | null;
  runtime: number | null;
  status: string;
  in_cinemas: string | null;
  digital_release: string | null;
  physical_release: string | null;
  genres: string[];
  images: Images;
  ratings: Record<string, Rating>;
  certification: string | null;
  studio: string | null;
  collection: string | null;
  original_language: string | null;
  metadata_sources: string[];
  monitored: boolean;
  minimum_availability: MinimumAvailability;
  quality_profile_id: number;
  root_folder: string;
  path: string;
  tags: number[];
  added: string | null;
  last_refresh: string | null;
  has_file: boolean;
  file: MediaFile | null;
}

export interface SeriesStats {
  episode_count?: number;
  episode_file_count?: number;
  monitored_aired?: number;
  monitored_have?: number;
  next_airing?: string | null;
  previous_airing?: string | null;
  size_on_disk?: number;
}

export interface SeasonStats {
  total: number;
  files: number;
  aired: number;
  monitored: number;
}

export interface Season {
  number: number;
  monitored: boolean;
  images: Images;
  stats: SeasonStats;
}

export type SeriesType = "standard" | "daily" | "anime";

export interface Series {
  id: number;
  type: "series";
  tvdb_id: number | null;
  tmdb_id: number | null;
  tvmaze_id: number | null;
  imdb_id: string | null;
  anilist_id: number | null;
  title: string;
  original_title: string | null;
  sort_title: string;
  alt_titles: string[];
  year: number | null;
  overview: string | null;
  runtime: number | null;
  status: string;
  network: string | null;
  air_time: string | null;
  genres: string[];
  images: Images;
  ratings: Record<string, Rating>;
  certification: string | null;
  original_language: string | null;
  series_type: SeriesType;
  episode_source: string;
  metadata_sources: string[];
  monitored: boolean;
  monitor_new_seasons: boolean;
  season_folder: boolean;
  quality_profile_id: number;
  root_folder: string;
  path: string;
  tags: number[];
  added: string | null;
  last_refresh: string | null;
  stats: SeriesStats;
  seasons?: Season[];
}

export interface Episode {
  id: number;
  series_id: number;
  season: number;
  number: number;
  absolute_number: number | null;
  title: string | null;
  overview: string | null;
  air_date: string | null;
  air_date_utc: string | null;
  runtime: number | null;
  monitored: boolean;
  has_file: boolean;
  file_id: number | null;
  file: MediaFile | null;
  series_title?: string;
  series_poster?: string | null;
}

export interface LookupIds {
  tmdb?: number | null;
  imdb?: string | null;
  tvdb?: number | null;
  tvmaze?: number | null;
  anilist?: number | null;
}

export interface LookupResult {
  provider?: string;
  sources?: string[];
  metadata_sources?: string[];
  ids: LookupIds;
  title: string;
  original_title?: string | null;
  alt_titles?: string[];
  year?: number | null;
  overview?: string | null;
  runtime?: number | null;
  status?: string | null;
  network?: string | null;
  genres?: string[];
  images?: Images;
  ratings?: Record<string, Rating>;
  is_anime?: boolean;
  popularity?: number;
  existing_id: number | null;
  seasons?: { number: number }[];
}

// ---------------------------------------------------------------- releases / decisions
export interface Release {
  guid: string;
  title: string;
  indexer_id: number;
  indexer: string;
  protocol: "torrent" | "usenet";
  download_url: string;
  info_url: string | null;
  size: number;
  publish_date: string | null;
  age_hours: number;
  seeders: number | null;
  leechers: number | null;
  grabs: number | null;
  info_hash: string | null;
  magnet: string | null;
  categories: number[];
  imdb_id: string | null;
  tmdb_id: number | null;
  tvdb_id: number | null;
  tvmaze_id: number | null;
  flags: string[];
  indexer_priority: number;
}

export interface ParsedRelease {
  raw: string;
  title: string;
  clean_title: string;
  year: number | null;
  is_tv: boolean;
  seasons: number[];
  episodes: number[];
  absolute_episodes: number[];
  air_date: string | null;
  full_season: boolean;
  multi_season: boolean;
  complete_series: boolean;
  is_anime: boolean;
  special: boolean;
  source: string;
  resolution: number;
  quality: string;
  revision: number;
  real: number;
  codec: string | null;
  hdr: string[];
  audio: string[];
  audio_channels: string | null;
  three_d: boolean;
  hardcoded_subs: boolean;
  languages: string[];
  subbed: boolean;
  edition: string | null;
  release_group: string | null;
  crc: string | null;
}

export interface Decision {
  release: Release;
  parsed: ParsedRelease;
  approved: boolean;
  rejections: string[];
  temporary: boolean;
  quality: string;
  format_score: number;
  formats: string[];
  language_match: boolean;
  episode_ids: number[];
  movie_id: number | null;
  series_id: number | null;
}

export interface ReleaseSearchResult {
  releases: Decision[];
  errors: string[];
  indexers: number;
}

// ---------------------------------------------------------------- config
export interface QualityDef {
  name: string;
  source: string;
  resolution: number;
  rank: number;
  min_mb_min: number;
  max_mb_min: number;
}

export interface ProfileItem {
  quality: string;
  allowed: boolean;
}

export interface QualityProfile {
  id: number;
  name: string;
  items: ProfileItem[];
  cutoff: string;
  upgrade_allowed: boolean;
  languages: string[];
  language_mode: "require" | "prefer";
  format_scores: Record<string, number>;
  min_format_score: number;
  cutoff_format_score: number;
  required_terms: string[];
  ignored_terms: string[];
}

export interface CFCondition {
  type: string;
  value: string;
  negate: boolean;
  required: boolean;
}

export interface CustomFormat {
  id: number;
  name: string;
  conditions: CFCondition[];
}

export interface CFTestResult {
  parsed: ParsedRelease;
  formats: string[];
  profiles: { id: number; name: string; score: number; quality_allowed: boolean }[];
}

export type RootMediaType = "movie" | "series" | "anime";

export interface RootFolder {
  id: number;
  path: string;
  media_type: RootMediaType;
  free_space: number | null;
  total_space: number | null;
  accessible: boolean;
}

export interface Tag {
  id: number;
  label: string;
}

export interface LimitState {
  kind: "query" | "grab";
  limit: number;
  used: number;
  remote_used: number | null;
  reserve: number;
  window_start: string;
  window_end: string | null;
  next_slot: string | null;
  remaining: number | null;
  remaining_auto: number | null;
  percent: number;
}

export interface RemoteLimits {
  api_current?: number | null;
  api_max?: number | null;
  grab_current?: number | null;
  grab_max?: number | null;
  api_oldest?: string | null;
  grab_oldest?: string | null;
  api_next?: string | null;
  grab_next?: string | null;
  seen?: string; // last time the indexer reported counters
  checked?: string; // last time we asked
  supported?: boolean; // false: the indexer answered without apilimits
  raw?: Record<string, string>;
}

export interface IndexerBase {
  name: string;
  kind: "newznab" | "torznab";
  url: string;
  api_path: string;
  api_key: string;
  movie_categories: number[];
  tv_categories: number[];
  anime_categories: number[];
  additional_params: string;
  enabled: boolean;
  enable_rss: boolean;
  enable_auto_search: boolean;
  enable_interactive_search: boolean;
  priority: number;
  minimum_seeders: number;
  seed_ratio: number | null;
  seed_time: number | null;
  download_client_id: number | null;
  tags: number[];
  query_limit: number;
  grab_limit: number;
  limit_window_hours: number;
  limit_mode: "rolling" | "fixed";
  limit_reset_hour: number;
  grab_reserve: number;
  query_reserve: number;
  min_request_interval: number;
  sync_remote_limits: boolean;
}

export interface Indexer extends IndexerBase {
  id: number;
  protocol: "torrent" | "usenet";
  capabilities: Record<string, unknown> | null;
  disabled_until: string | null;
  failure_count: number;
  last_error: string | null;
  remote_limits: RemoteLimits | null;
  sync_source: Record<string, unknown> | null;
  usage?: { query: LimitState; grab: LimitState };
}

export interface LimitPreset {
  name: string;
  query_limit: number;
  grab_limit: number;
  limit_window_hours: number;
  limit_mode: "rolling" | "fixed";
  limit_reset_hour?: number;
}

export interface IndexerPresets {
  limits: LimitPreset[];
  categories: { movie: number[]; tv: number[]; anime: number[] };
}

export interface IndexerUsageSummary {
  id: number;
  name: string;
  enabled: boolean;
  protocol: "torrent" | "usenet";
  paused_until: string | null;
  last_error: string | null;
  limit_mode: "rolling" | "fixed";
  window_hours: number;
  query: LimitState;
  grab: LimitState;
}

export interface HistogramBucket {
  hour: string;
  query: number;
  grab: number;
  failed: number;
}

export interface ForecastPoint {
  at: string;
  available: number;
}

export interface IndexerEvent {
  id: number;
  kind: string;
  timestamp: string;
  success: boolean;
  manual: boolean;
  elapsed_ms: number;
  results: number;
  detail: string | null;
}

export interface IndexerUsageDetail {
  indexer: Indexer;
  histogram: HistogramBucket[];
  forecast: { query: ForecastPoint[]; grab: ForecastPoint[] };
  events: IndexerEvent[];
}

export interface DownloadClientBase {
  name: string;
  kind: string;
  enabled: boolean;
  priority: number;
  host: string;
  port: number;
  use_ssl: boolean;
  url_base: string;
  username: string;
  password: string;
  api_key: string;
  movie_category: string;
  tv_category: string;
  remove_completed: boolean;
  remove_failed: boolean;
  add_paused: boolean;
  settings: Record<string, string | number | boolean>;
  tags: number[];
}

export interface DownloadClient extends DownloadClientBase {
  id: number;
  protocol: "torrent" | "usenet";
}

export interface DownloadClientSchema {
  kind: string;
  protocol: "torrent" | "usenet";
  port?: number;
}

export interface RemotePathMapping {
  id: number;
  host: string;
  remote_path: string;
  local_path: string;
}

export interface NotificationBase {
  name: string;
  kind: string;
  enabled: boolean;
  on_grab: boolean;
  on_import: boolean;
  on_upgrade: boolean;
  on_failure: boolean;
  on_health: boolean;
  settings: Record<string, string>;
}

export interface Notification extends NotificationBase {
  id: number;
}

export interface NotificationSchema {
  kind: string;
  fields: string[];
}

export interface MetadataProviderStatus {
  name: string;
  movies: boolean;
  series: boolean;
  needs_key: boolean;
  available: boolean;
  enabled: boolean;
}

// ---------------------------------------------------------------- settings
export interface MetadataSettings {
  language: string;
  fallback_language: string;
  movie_providers: string[];
  series_providers: string[];
  anime_providers: string[];
  enabled: Record<string, boolean>;
  keys: { tmdb: string; tvdb: string; tvdb_pin: string; omdb: string };
  cache_hours: number;
  refresh_interval_hours: number;
}

export interface MediaSettings {
  rename: boolean;
  movie_folder: string;
  movie_file: string;
  series_folder: string;
  season_folder: string;
  specials_folder: string;
  episode_file: string;
  daily_file: string;
  anime_file: string;
  multi_episode_style: "extend" | "duplicate";
  colon_replacement: string;
  use_hardlinks: boolean;
  recycle_bin: string;
  recycle_bin_days: number;
  delete_empty_folders: boolean;
  import_extra_files: boolean;
  extra_extensions: string;
  sample_max_mb: number;
  min_free_space_mb: number;
  file_chmod: string;
  upgrade_propers: boolean;
  quality_sizes?: Record<string, { min?: number; max?: number }>;
}

export interface DownloadSettings {
  completed_handling: boolean;
  redownload_failed: boolean;
  check_interval_seconds: number;
  stalled_timeout_hours: number;
}

export interface IndexerSettings {
  rss_interval_minutes: number;
  limits_poll_minutes: number;
  minimum_age_minutes: number;
  retention_days: number;
  maximum_size_mb: number;
  rss_respect_limits: boolean;
  search_respect_limits: boolean;
  backoff_minutes: number[];
}

export interface WantedSettings {
  auto_search_interval_hours: number;
  batch_size: number;
  search_on_add: boolean;
  cutoff_unmet_search: boolean;
  min_hours_between_item_searches: number;
}

export interface BackupSettings {
  interval_days: number;
  retention_days: number;
}

export interface UiSettings {
  language: string;
  first_day_of_week: number;
  date_format: string;
  time_format: string;
}

export interface AuthSettings {
  method: "none" | "forms";
  username: string;
  password?: string;
}

export interface AllSettings {
  metadata: MetadataSettings;
  media: MediaSettings;
  downloads: DownloadSettings;
  indexers: IndexerSettings;
  wanted: WantedSettings;
  backup: BackupSettings;
  ui: UiSettings;
  auth: AuthSettings;
}

export type SettingsSection = keyof AllSettings;

// ---------------------------------------------------------------- system
export interface BackupInfo {
  name: string;
  kind: "manual" | "scheduled" | "migration" | "restore";
  size: number;
  created: string;
}

export interface BackupListing {
  backups: BackupInfo[];
  restore_pending: boolean;
  folder: string;
}

export interface SystemStatus {
  app: string;
  version: string;
  started: string;
  python: string;
  os: string;
  config_dir: string;
  db: string;
  api_key: string;
  url_base: string;
  movies: number;
  series: number;
  docker: boolean;
}

export interface HealthIssue {
  level: "error" | "warning" | "info";
  source: string;
  message: string;
}

export interface Health {
  issues: HealthIssue[];
  checked: string | null;
}

export interface TaskInfo {
  name: string;
  label: string;
  interval_seconds: number;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  last_duration_ms: number;
  last_error: string | null;
  running: boolean;
}

export interface Command {
  id: number;
  name: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "completed" | "failed";
  queued: string;
  started: string | null;
  ended: string | null;
  result: unknown;
  error: string | null;
}

export interface LogRecord {
  id: number;
  time: string;
  level: string;
  logger: string;
  message: string;
}

export interface FsEntry {
  name: string;
  path: string;
  size?: number;
}

export interface FsListing {
  path: string;
  parent: string | null;
  dirs: FsEntry[];
  files: FsEntry[];
  free_space?: number | null;
}

export interface DiskSpace {
  path: string;
  total: number;
  free: number;
}

// ---------------------------------------------------------------- activity
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
