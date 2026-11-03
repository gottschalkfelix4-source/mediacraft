// System.

export interface ChangeEntry {
  sha: string;
  title: string;
  body: string;
  date: string | null;
  url: string | null;
}

export interface UpdateInfo {
  current: { version: string; build: string; commit: string | null; build_date: string; repo: string };
  latest: ChangeEntry | null;
  update_available: boolean | null;
  changes: ChangeEntry[];
  error: string | null;
  checked: string;
}

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
  tools?: { mediainfo: string | null; unpack: string[] };
  build?: string;
  commit?: string;
  build_date?: string;
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
