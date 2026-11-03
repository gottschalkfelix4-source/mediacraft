// Config.
import type { ParsedRelease } from "./releases";

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
  on_delete: boolean;
  on_rename: boolean;
  on_limit: boolean;
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
