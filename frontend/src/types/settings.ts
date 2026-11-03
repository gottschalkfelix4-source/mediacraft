// Settings.

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
  unpack_archives: boolean;
  probe_files: boolean;
  probe_update_languages: boolean;
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
  local_bypass: boolean;
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
  importlists: { sync_interval_hours: number };
  ui: UiSettings;
  auth: AuthSettings;
}

export type SettingsSection = keyof AllSettings;
