// Library: movies, series, episodes, files, lookups.

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
