// Typed API client for the MediaCraft backend (/api/v1).
import type * as T from "./types";

declare global {
  interface Window {
    __MC_BASE__?: string;
  }
}

/** URL base when MediaCraft runs under a sub path (e.g. "/mediacraft"), injected by the server. */
export const URL_BASE = (typeof window !== "undefined" ? (window.__MC_BASE__ ?? "") : "").replace(/\/+$/, "");
export const API_BASE = `${URL_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Query): string {
  if (!params) return "";
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: () => void) {
  unauthorizedHandler = fn;
}

async function request<R>(method: string, path: string, body?: unknown, params?: Query): Promise<R> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${qs(params)}`, init);
  } catch (e) {
    throw new ApiError(0, "Server nicht erreichbar");
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    if (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
      const d = (data as { detail: unknown }).detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x?.msg ?? JSON.stringify(x)).join("; ") : JSON.stringify(d);
    } else if (typeof data === "string" && data) {
      msg = data.slice(0, 300);
    }
    if (res.status === 401 && unauthorizedHandler && !path.startsWith("/auth/")) unauthorizedHandler();
    throw new ApiError(res.status, msg);
  }
  return data as R;
}

const get = <R>(p: string, params?: Query) => request<R>("GET", p, undefined, params);
const post = <R>(p: string, body?: unknown, params?: Query) => request<R>("POST", p, body ?? {}, params);
const put = <R>(p: string, body?: unknown) => request<R>("PUT", p, body ?? {});
const del = <R>(p: string, params?: Query) => request<R>("DELETE", p, undefined, params);

export interface Ok {
  ok: boolean;
}

export const api = {
  // ------------------------------------------------------------- auth
  authStatus: () => get<T.AuthStatus>("/auth/status"),
  login: (username: string, password: string, remember: boolean) => post<Ok>("/auth/login", { username, password, remember }),
  logout: () => post<Ok>("/auth/logout"),

  // ------------------------------------------------------------- system
  status: () => get<T.SystemStatus>("/system/status"),
  regenerateApiKey: () => post<{ api_key: string }>("/system/apikey/regenerate"),
  health: () => get<T.Health>("/system/health"),
  refreshHealth: () => post<T.Health>("/system/health/refresh"),
  tasks: () => get<T.TaskInfo[]>("/system/tasks"),
  runTask: (name: string) => post<T.Command>(`/system/tasks/${encodeURIComponent(name)}/run`),
  commands: () => get<T.Command[]>("/commands"),
  command: (name: string, params?: Record<string, unknown>) => post<T.Command>("/commands", { name, params: params ?? {} }),
  logs: (level = "", limit = 500) => get<T.LogRecord[]>("/system/logs", { level, limit }),
  settings: () => get<T.AllSettings>("/settings"),
  saveSettings: <K extends T.SettingsSection>(section: K, body: Partial<T.AllSettings[K]>) =>
    put<T.AllSettings[K]>(`/settings/${section}`, body),
  filesystem: (path = "", includeFiles = false) => get<T.FsListing>("/filesystem", { path, include_files: includeFiles || undefined }),
  diskspace: () => get<T.DiskSpace[]>("/diskspace"),
  restart: () => post<Ok>("/system/restart"),
  updates: (force: boolean) => get<T.UpdateInfo>("/system/updates", { force: force || undefined }),
  backups: () => get<T.BackupListing>("/system/backups"),
  createBackup: () => post<T.BackupInfo>("/system/backups"),
  deleteBackup: (name: string) => del<Ok>(`/system/backups/${encodeURIComponent(name)}`),
  backupUrl: (name: string) => `${API_BASE}/system/backups/${encodeURIComponent(name)}`,
  restoreBackup: (name: string) => post<Ok>(`/system/backups/${encodeURIComponent(name)}/restore`),
  restoreUpload: async (file: File) => {
    const res = await fetch(`${API_BASE}/system/backups-upload/restore`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/zip" },
      body: file,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new ApiError(res.status, (data && typeof data.detail === "string" && data.detail) || `HTTP ${res.status}`);
    }
    return (await res.json()) as Ok;
  },

  // ------------------------------------------------------------- config
  qualities: () => get<T.QualityDef[]>("/qualities"),
  profiles: () => get<T.QualityProfile[]>("/qualityprofiles"),
  createProfile: (b: Partial<T.QualityProfile>) => post<T.QualityProfile>("/qualityprofiles", b),
  updateProfile: (id: number, b: Partial<T.QualityProfile>) => put<T.QualityProfile>(`/qualityprofiles/${id}`, b),
  deleteProfile: (id: number) => del<Ok>(`/qualityprofiles/${id}`),
  customFormats: () => get<T.CustomFormat[]>("/customformats"),
  createCustomFormat: (b: Partial<T.CustomFormat>) => post<T.CustomFormat>("/customformats", b),
  updateCustomFormat: (id: number, b: Partial<T.CustomFormat>) => put<T.CustomFormat>(`/customformats/${id}`, b),
  deleteCustomFormat: (id: number) => del<Ok>(`/customformats/${id}`),
  testCustomFormat: (title: string, size = 0) => post<T.CFTestResult>("/customformats/test", { title, size }),
  rootFolders: () => get<T.RootFolder[]>("/rootfolders"),
  addRootFolder: (path: string, media_type: T.RootMediaType) => post<T.RootFolder>("/rootfolders", { path, media_type }),
  deleteRootFolder: (id: number) => del<Ok>(`/rootfolders/${id}`),
  tags: () => get<T.Tag[]>("/tags"),
  createTag: (label: string) => post<T.Tag>("/tags", { label }),
  deleteTag: (id: number) => del<Ok>(`/tags/${id}`),

  indexers: () => get<T.Indexer[]>("/indexers"),
  indexer: (id: number) => get<T.Indexer>(`/indexers/${id}`),
  indexerPresets: () => get<T.IndexerPresets>("/indexers/presets"),
  createIndexer: (b: Partial<T.IndexerBase>) => post<T.Indexer>("/indexers", b),
  updateIndexer: (id: number, b: Partial<T.IndexerBase>) => put<T.Indexer>(`/indexers/${id}`, b),
  deleteIndexer: (id: number) => del<Ok>(`/indexers/${id}`),
  testIndexer: (b: Partial<T.IndexerBase> & { id?: number }) =>
    post<{ ok: boolean; capabilities: Record<string, unknown> }>("/indexers/test", b),
  indexerCaps: (id: number) => post<Record<string, unknown>>(`/indexers/${id}/caps`),
  unpauseIndexer: (id: number) => post<T.Indexer>(`/indexers/${id}/unpause`),
  refreshIndexerLimits: (id: number) => post<T.Indexer>(`/indexers/${id}/limits`),
  indexerUsage: (id: number, hours = 48) => get<T.IndexerUsageDetail>(`/indexers/${id}/usage`, { hours }),
  resetIndexerUsage: (id: number) => del<{ deleted: number }>(`/indexers/${id}/usage`),
  indexersUsage: () => get<T.IndexerUsageSummary[]>("/indexers-usage"),

  downloadClients: () => get<T.DownloadClient[]>("/downloadclients"),
  downloadClientSchema: () => get<T.DownloadClientSchema[]>("/downloadclients/schema"),
  createDownloadClient: (b: Partial<T.DownloadClientBase>) => post<T.DownloadClient>("/downloadclients", b),
  updateDownloadClient: (id: number, b: Partial<T.DownloadClientBase>) => put<T.DownloadClient>(`/downloadclients/${id}`, b),
  deleteDownloadClient: (id: number) => del<Ok>(`/downloadclients/${id}`),
  testDownloadClient: (b: Partial<T.DownloadClientBase> & { id?: number }) =>
    post<{ ok: boolean; message: unknown }>("/downloadclients/test", b),
  remotePathMappings: () => get<T.RemotePathMapping[]>("/remotepathmappings"),
  createRemotePathMapping: (b: Omit<T.RemotePathMapping, "id">) => post<T.RemotePathMapping>("/remotepathmappings", b),
  updateRemotePathMapping: (id: number, b: Omit<T.RemotePathMapping, "id">) =>
    put<T.RemotePathMapping>(`/remotepathmappings/${id}`, b),
  deleteRemotePathMapping: (id: number) => del<Ok>(`/remotepathmappings/${id}`),

  notifications: () => get<T.Notification[]>("/notifications"),
  notificationSchema: () => get<T.NotificationSchema[]>("/notifications/schema"),
  createNotification: (b: T.NotificationBase) => post<T.Notification>("/notifications", b),
  updateNotification: (id: number, b: T.NotificationBase) => put<T.Notification>(`/notifications/${id}`, b),
  deleteNotification: (id: number) => del<Ok>(`/notifications/${id}`),
  testNotification: (b: T.NotificationBase & { id?: number }) => post<Ok>("/notifications/test", b),
  qualityDefinitions: () => get<T.QualityDefinition[]>("/qualitydefinitions"),
  saveQualityDefinitions: (b: T.QualityDefinition[]) => put<T.QualityDefinition[]>("/qualitydefinitions", b),
  recycleBin: () => get<T.RecycleListing>("/recyclebin"),
  recycleRestore: (path: string) => post<{ ok: boolean; restored: string }>("/recyclebin/restore", { path }),
  recycleDelete: (path: string) => post<Ok>("/recyclebin/delete", { path }),
  recycleEmpty: () => post<{ removed: number }>("/recyclebin/empty"),
  importListSchema: () => get<T.ImportListSchema[]>("/importlists/schema"),
  importLists: () => get<T.ImportList[]>("/importlists"),
  createImportList: (b: Partial<T.ImportList>) => post<T.ImportList>("/importlists", b),
  updateImportList: (id: number, b: Partial<T.ImportList>) => put<T.ImportList>(`/importlists/${id}`, b),
  deleteImportList: (id: number) => del<Ok>(`/importlists/${id}`),
  testImportList: (b: Partial<T.ImportList>) => post<T.ImportListTest>("/importlists/test", b),
  syncImportList: (id: number) => post<{ added: string[]; failed: string[]; existing: number; excluded: number }>(`/importlists/${id}/sync`),
  exclusions: () => get<T.ImportListExclusion[]>("/exclusions"),
  deleteExclusion: (id: number) => del<Ok>(`/exclusions/${id}`),
  collections: () => get<T.MovieCollection[]>("/collections"),
  addCollectionMovies: (
    id: number,
    b: { tmdb_ids?: number[]; quality_profile_id: number; root_folder: string; monitored: boolean; minimum_availability: string; search: boolean },
  ) => post<{ added: string[]; failed: string[] }>(`/collections/${id}/add`, b),
  delayProfiles: () => get<T.DelayProfile[]>("/delayprofiles"),
  createDelayProfile: (b: Partial<T.DelayProfile>) => post<T.DelayProfile>("/delayprofiles", b),
  updateDelayProfile: (id: number, b: Partial<T.DelayProfile>) => put<T.DelayProfile>(`/delayprofiles/${id}`, b),
  deleteDelayProfile: (id: number) => del<Ok>(`/delayprofiles/${id}`),
  pending: () => get<T.PendingRelease[]>("/pending"),
  grabPending: (id: number) => post<{ grabbed: number; errors: string[] }>(`/pending/${id}/grab`),
  deletePending: (id: number) => del<Ok>(`/pending/${id}`),
  metadataProviders: () => get<T.MetadataProviderStatus[]>("/metadata/providers"),

  // ------------------------------------------------------------- media
  lookupMovie: (term: string) => get<T.LookupResult[]>("/lookup/movie", { term }),
  lookupSeries: (term: string) => get<T.LookupResult[]>("/lookup/series", { term }),

  movies: () => get<T.Movie[]>("/movies"),
  movie: (id: number) => get<T.Movie>(`/movies/${id}`),
  addMovie: (b: {
    ids: T.LookupIds;
    quality_profile_id: number;
    root_folder: string;
    monitored: boolean;
    minimum_availability: T.MinimumAvailability;
    tags: number[];
    search: boolean;
    path?: string;
  }) => post<T.Movie>("/movies", b),
  updateMovie: (id: number, b: Partial<T.Movie> & { move_files?: boolean }) => put<T.Movie>(`/movies/${id}`, b),
  rematchMovie: (id: number, ids: T.LookupIds) => post<T.Movie>(`/movies/${id}/rematch`, { ids }),
  bulkUpdateMovies: (b: T.BulkEdit) => put<T.BulkResult>("/movies", b),
  bulkDeleteMovies: (ids: number[], delete_files: boolean, add_exclusion = false) =>
    post<{ deleted: number }>("/movies/delete", { ids, delete_files, add_exclusion }),
  deleteMovie: (id: number, deleteFiles: boolean, addExclusion = false) =>
    del<Ok>(`/movies/${id}`, { delete_files: deleteFiles, add_exclusion: addExclusion || undefined }),
  deleteMovieFile: (id: number) => del<T.Movie>(`/movies/${id}/file`),
  movieReleases: (id: number) => get<T.ReleaseSearchResult>(`/movies/${id}/releases`),
  movieHistory: (id: number) => get<T.HistoryRecord[]>(`/movies/${id}/history`),
  movieRename: (id: number) => get<T.RenamePreview[]>(`/movies/${id}/rename`),

  seriesList: () => get<T.Series[]>("/series"),
  series: (id: number) => get<T.Series>(`/series/${id}`),
  addSeries: (b: {
    ids: T.LookupIds;
    quality_profile_id: number;
    root_folder: string;
    monitored: boolean;
    monitor: string;
    series_type: T.SeriesType;
    season_folder: boolean;
    tags: number[];
    episode_source: string;
    search: boolean;
    path?: string;
  }) => post<T.Series>("/series", b),
  updateSeries: (id: number, b: Partial<T.Series> & { move_files?: boolean }) => put<T.Series>(`/series/${id}`, b),
  bulkUpdateSeries: (b: T.BulkEdit) => put<T.BulkResult>("/series", b),
  bulkDeleteSeries: (ids: number[], delete_files: boolean, add_exclusion = false) =>
    post<{ deleted: number }>("/series/delete", { ids, delete_files, add_exclusion }),
  updateSeason: (id: number, season: number, monitored: boolean) =>
    put<T.Series>(`/series/${id}/seasons/${season}`, { monitored }),
  seriesMonitoring: (id: number, monitor: string) => post<T.Series>(`/series/${id}/monitoring`, { monitor }),
  rematchSeries: (id: number, ids: T.LookupIds) => post<T.Series>(`/series/${id}/rematch`, { ids }),
  deleteSeries: (id: number, deleteFiles: boolean, addExclusion = false) =>
    del<Ok>(`/series/${id}`, { delete_files: deleteFiles, add_exclusion: addExclusion || undefined }),
  episodes: (seriesId: number) => get<T.Episode[]>(`/series/${seriesId}/episodes`),
  monitorEpisodes: (ids: number[], monitored: boolean) => put<Ok>("/episodes/monitor", { ids, monitored }),
  deleteEpisodeFile: (fileId: number) => del<Ok>(`/episodefiles/${fileId}`),
  seriesReleases: (id: number, opts: { season?: number; episode_id?: number }) =>
    get<T.ReleaseSearchResult>(`/series/${id}/releases`, opts),
  seriesHistory: (id: number) => get<T.HistoryRecord[]>(`/series/${id}/history`),
  seriesRename: (id: number) => get<T.RenamePreview[]>(`/series/${id}/rename`),

  grabRelease: (indexer_id: number, guid: string, force = false) =>
    post<Record<string, unknown>>("/releases/grab", { indexer_id, guid, force }),
  parse: (title: string) => get<{ parsed: T.ParsedRelease }>("/parse", { title }),

  calendar: (start: string, end: string, unmonitored = false) =>
    get<T.CalendarItem[]>("/calendar", { start, end, unmonitored: unmonitored || undefined }),
  wantedMissing: () => get<T.WantedResult>("/wanted/missing"),
  wantedCutoff: () => get<T.WantedResult>("/wanted/cutoff"),

  libraryImport: (rootFolderId: number) => get<T.UnmappedFolder[]>("/libraryimport", { root_folder_id: rootFolderId }),
  libraryImportLookup: (item: Pick<T.UnmappedFolder, "title" | "year" | "ids" | "media_type">) =>
    post<T.LookupResult[]>("/libraryimport/lookup", item),
  manualImportScan: (path: string) => get<T.ManualImportItem[]>("/manualimport", { path }),
  manualImport: (
    items: { path: string; movie_id?: number | null; series_id?: number | null; episode_ids?: number[]; quality?: string; languages?: string[] }[],
    mode: "copy" | "move",
  ) => post<T.ManualImportResult[]>("/manualimport", { items, mode }),

  queue: () => get<T.QueueItem[]>("/queue"),
  removeQueue: (id: number, opts: { remove_from_client: boolean; blocklist: boolean; search_again: boolean }) =>
    del<Ok>(`/queue/${id}`, opts),
  retryQueueImport: (id: number) => post<{ ok: boolean; queued?: boolean; messages: string[] }>(`/queue/${id}/import`),
  history: (page: number, pageSize: number, event: string) =>
    get<T.HistoryPage>("/history", { page, page_size: pageSize, event }),
  markFailed: (id: number) => post<Ok>(`/history/${id}/failed`),
  blocklist: () => get<T.BlocklistItem[]>("/blocklist"),
  deleteBlocklist: (id: number) => del<Ok>(`/blocklist/${id}`),
  clearBlocklist: () => del<{ deleted: number }>("/blocklist"),
  dashboard: () => get<T.Dashboard>("/dashboard"),
  stats: (weeks: number) => get<T.StatsData>("/stats", { weeks }),
};

/** After a restart: wait until the server answers again (gives up after ~2 minutes). */
export async function waitForServer(): Promise<boolean> {
  await new Promise((r) => setTimeout(r, 2500));
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${URL_BASE}/ping`, { cache: "no-store" });
      if (r.ok) return true;
    } catch {
      /* still down */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}

export function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}
