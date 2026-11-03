// Releases / decisions.

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
