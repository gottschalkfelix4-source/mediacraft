import { useEffect, useId, useState, type ComponentType, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, BarChart3, CalendarDays, CheckCircle2, Download, Film, HardDrive, HeartPulse, Info, LayoutGrid, ListVideo, PauseCircle, PieChart, Plus, Rss, SearchX, Sparkles, Tv, type LucideIcon,
} from "lucide-react";
import { api } from "../../api";
import { Badge, CountUp, Empty, Skeleton } from "../../components/ui";
import { Poster } from "../../components/Media";
import { UsageMeter, windowLabel } from "../../components/Usage";
import { useCommand, useMovies, useNow, useSeriesList } from "../../hooks";
import {
  epCode, fmtDate, fmtDateTime, fmtDuration, fmtNumber, fmtSize, fmtTime, HISTORY_EVENT_LABELS, MONTHS, parseDate, QUEUE_STATUS_LABELS, relTime, WEEKDAYS, WEEKDAYS_LONG,
} from "../../format";
import type { CalendarItem } from "../../types";
import { greeting, type WidgetMeta, type WidgetPlacement } from "./layout";

export interface WidgetDef extends WidgetMeta {
  title: string;
  description: string;
  icon: LucideIcon;
  /** bare widgets bring their own surface instead of the card frame with header */
  bare?: boolean;
  link?: { to: string; label: string };
  Component: ComponentType;
}

const DONE_STATES = ["imported", "failed", "removed"];
const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 60_000 });
const useQueue = (refetchInterval = 30_000) => useQuery({ queryKey: ["queue"], queryFn: api.queue, refetchInterval });
const int = (n: number) => fmtNumber(Math.round(n));

// ------------------------------------------------------------------ welcome
function WelcomeWidget() {
  const now = useNow(5_000);
  const dash = useDashboard();
  const queue = useQueue();
  const command = useCommand();
  const active = (queue.data ?? []).filter((q) => !DONE_STATES.includes(q.status)).length;
  const today = (dash.data?.upcoming ?? []).filter((it) => parseDate(it.date)?.toDateString() === now.toDateString()).length;
  const missing = dash.data ? dash.data.movies.missing + dash.data.series.missing : null;

  return (
    <div className="hero">
      <div className="hero-orb a" />
      <div className="hero-orb b" />
      <div className="hero-main">
        <span className="hero-eyebrow">MediaCraft · Übersicht</span>
        <h2>
          <span className="gradient-text">{greeting(now)}</span>
        </h2>
        <div className="hero-summary">
          <span>
            <Download size={15} /> <strong>{active}</strong> {active === 1 ? "Download" : "Downloads"} aktiv
          </span>
          <span>
            <CalendarDays size={15} /> <strong>{today}</strong> heute erwartet
          </span>
          {missing !== null && (
            <span>
              <SearchX size={15} /> <strong>{fmtNumber(missing)}</strong> fehlend
            </span>
          )}
        </div>
        <div className="hero-actions">
          <Link to="/movies/add" className="btn btn-primary">
            <Plus size={16} /> Film
          </Link>
          <Link to="/series/add" className="btn">
            <Plus size={16} /> Serie
          </Link>
          <button className="btn" onClick={() => command("rss_sync")} title="RSS-Sync starten">
            <Rss size={15} /> RSS-Sync
          </button>
          <button className="btn" onClick={() => command("wanted_search")} title="Alle fehlenden Filme und Episoden suchen">
            <SearchX size={15} /> Fehlende suchen
          </button>
        </div>
      </div>
      <div className="hero-clock" aria-hidden="true">
        <div className="hero-time">
          {String(now.getHours()).padStart(2, "0")}
          <span className="colon">:</span>
          {String(now.getMinutes()).padStart(2, "0")}
        </div>
        <div className="hero-date">
          {WEEKDAYS_LONG[now.getDay()]}, {now.getDate()}. {MONTHS[now.getMonth()]} {now.getFullYear()}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ key figures
function StatsWidget() {
  const { data } = useDashboard();
  const disk = useQuery({ queryKey: ["diskspace"], queryFn: api.diskspace, staleTime: 300_000 });
  if (!data)
    return (
      <div className="stat-grid">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="stat">
            <Skeleton lines={2} />
          </div>
        ))}
      </div>
    );

  const missing = data.movies.missing + data.series.missing;
  const stats: { icon: LucideIcon; label: string; value: number; format?: (n: number) => string; sub: string; to: string; tile?: string; tone?: string }[] = [
    { icon: Film, label: "Filme", value: data.movies.total, sub: `${fmtNumber(data.movies.with_file)} vorhanden`, to: "/movies" },
    { icon: Tv, label: "Serien", value: data.series.total, sub: `${fmtNumber(data.series.episodes)} Episoden`, to: "/series", tile: "var(--accent-2)" },
    { icon: ListVideo, label: "Episoden-Dateien", value: data.series.episode_files, sub: `von ${fmtNumber(data.series.episodes)}`, to: "/series", tile: "var(--violet)" },
    { icon: SearchX, label: "Fehlend", value: missing, sub: `${data.movies.missing} Filme · ${data.series.missing} Episoden`, to: "/wanted", tone: missing > 0 ? "warning" : undefined, tile: missing > 0 ? undefined : "var(--success)" },
    {
      icon: HardDrive,
      label: "Belegt",
      value: data.size_on_disk,
      format: (n) => fmtSize(n),
      sub: disk.data?.length ? `${fmtSize(disk.data.reduce((a, d) => a + d.free, 0))} frei` : "Größe auf Disk",
      to: "/system/status",
      tile: "var(--info)",
    },
    { icon: Download, label: "Warteschlange", value: data.queue, sub: "aktive Downloads", to: "/activity" },
  ];

  return (
    <div className="stat-grid">
      {stats.map((s, i) => (
        <Link key={s.label} to={s.to} className={`stat ${s.tone ? `stat-${s.tone}` : ""}`} style={{ "--i": i, "--tile": s.tile } as CSSProperties}>
          <span className="stat-icon">
            <s.icon size={20} />
          </span>
          <div>
            <div className="stat-value">
              <CountUp value={s.value} format={s.format ?? int} />
            </div>
            <div className="stat-label">{s.label}</div>
            <div className="stat-sub">{s.sub}</div>
          </div>
        </Link>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ upcoming
function UpcomingWidget() {
  const { data } = useDashboard();
  const now = useNow(30_000);
  if (!data) return <Skeleton lines={5} />;
  if (data.upcoming.length === 0) return <Empty icon={<CalendarDays size={32} />} title="Nichts in den nächsten 7 Tagen" />;
  return (
    <div className="widget-scroll">
      <UpcomingList items={data.upcoming} now={now} />
    </div>
  );
}

function UpcomingList({ items, now }: { items: CalendarItem[]; now: Date }) {
  return (
    <ul className="upcoming">
      {items.map((it) => {
        const d = parseDate(it.date);
        const past = d && d.getTime() < now.getTime();
        const state = it.has_file ? "has-file" : past ? "missing" : "upcoming";
        return (
          <li key={`${it.type}-${it.id}-${it.release_type ?? ""}`} className={`upcoming-item state-${state}`}>
            <Link to={it.type === "movie" ? `/movies/${it.id}` : `/series/${it.series_id}`} className="upcoming-link">
              <Poster src={it.poster} title={it.title} kind={it.type === "movie" ? "movie" : "series"} className="poster-sm" />
              <div className="upcoming-body">
                <div className="strong">{it.title}</div>
                <div className="muted small">
                  {it.type === "episode" ? (
                    <>
                      {epCode(it.season, it.number)} {it.episode_title ? `· ${it.episode_title}` : ""}
                    </>
                  ) : (
                    <>{it.release_type === "cinema" ? "Kinostart" : it.release_type === "digital" ? "Digital" : "Disc"}</>
                  )}
                </div>
              </div>
              <div className="upcoming-date">
                {d ? (
                  <>
                    <div>
                      {WEEKDAYS[d.getDay()]} {String(d.getDate()).padStart(2, "0")}.{String(d.getMonth() + 1).padStart(2, "0")}.
                    </div>
                    {it.type === "episode" && <div className="muted small">{fmtTime(d)}</div>}
                  </>
                ) : (
                  "–"
                )}
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------------ downloads
function DownloadsWidget() {
  const { data } = useQueue(5_000);
  if (!data) return <Skeleton lines={4} />;
  const active = data.filter((q) => !DONE_STATES.includes(q.status));
  if (active.length === 0) return <Empty icon={<Download size={32} />} title="Keine aktiven Downloads" />;
  return (
    <ul className="dl-list widget-scroll">
      {active.slice(0, 10).map((q, i) => {
        const pct = Math.max(0, Math.min(100, q.import_progress ?? q.progress ?? 0));
        const live = q.status === "downloading" || q.import_progress !== null;
        return (
          <li key={q.id} className="dl-item" style={{ "--i": i } as CSSProperties}>
            <div className="dl-item-head">
              {q.media_type === "movie" ? <Film size={14} className="muted" /> : <Tv size={14} className="muted" />}
              <Link to="/activity" className="dl-item-title" title={q.title}>
                {q.target?.title ?? q.title}
              </Link>
              <Badge tone={q.stalled_since ? "warning" : live ? "accent" : "muted"}>{QUEUE_STATUS_LABELS[q.status] ?? q.status}</Badge>
            </div>
            <div className="progress progress-sm">
              <div className={`progress-bar tone-accent ${live ? "live" : ""}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="dl-item-meta">
              <span>
                {Math.round(pct)} % · {fmtSize(q.size - q.size_left)} / {fmtSize(q.size)}
              </span>
              <span>{q.eta_seconds ? `noch ${fmtDuration(q.eta_seconds)}` : q.quality}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------------ health
function HealthWidget() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const now = useNow(30_000);
  if (!health.data) return <Skeleton lines={3} />;
  const issues = health.data.issues;
  return (
    <>
      {issues.length === 0 ? (
        <div className="health-ok">
          <CheckCircle2 size={20} /> Keine Probleme gefunden
        </div>
      ) : (
        <ul className="issue-list widget-scroll">
          {issues.map((i, n) => (
            <li key={n} className={`issue issue-${i.level}`}>
              {i.level === "error" || i.level === "warning" ? <AlertTriangle size={16} /> : <Info size={16} />}
              <span>{i.message}</span>
              <Badge tone="muted">{i.source}</Badge>
            </li>
          ))}
        </ul>
      )}
      {health.data.checked && <div className="muted small mt-sm">Geprüft {relTime(health.data.checked, now)}</div>}
    </>
  );
}

// ------------------------------------------------------------------ library completeness rings
function Ring({ value, total, label, size = 116 }: { value: number; total: number; label: string; size?: number }) {
  const gid = `ring${useId().replace(/:/g, "")}`;
  const pct = total > 0 ? value / total : 0;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(pct));
    return () => cancelAnimationFrame(t);
  }, [pct]);
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div>
      <div className="ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} aria-hidden="true">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" style={{ stopColor: "var(--accent)" }} />
              <stop offset="100%" style={{ stopColor: "var(--accent-2)" }} />
            </linearGradient>
          </defs>
          <circle className="ring-track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={10} />
          <circle className="ring-val" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={10} strokeLinecap="round" stroke={`url(#${gid})`} strokeDasharray={c} strokeDashoffset={c * (1 - shown)} />
        </svg>
        <div className="ring-center">
          <span className="ring-pct">
            <CountUp value={pct * 100} format={(n) => `${Math.round(n)} %`} duration={1200} />
          </span>
          <span className="ring-label">{label}</span>
        </div>
      </div>
      <div className="ring-caption">
        {fmtNumber(value)} / {fmtNumber(total)}
      </div>
    </div>
  );
}

function LibraryWidget() {
  const { data } = useDashboard();
  if (!data) return <Skeleton lines={4} />;
  return (
    <div className="ring-row">
      <Ring value={data.movies.with_file} total={data.movies.total} label="Filme" />
      <Ring value={data.series.episode_files} total={data.series.episodes} label="Episoden" />
    </div>
  );
}

// ------------------------------------------------------------------ disks
function DiskWidget() {
  const { data } = useQuery({ queryKey: ["diskspace"], queryFn: api.diskspace, staleTime: 300_000 });
  if (!data) return <Skeleton lines={4} />;
  if (data.length === 0) return <Empty icon={<HardDrive size={32} />} title="Keine Stammordner" />;
  return (
    <div className="widget-scroll">
      {data.map((d) => {
        const used = d.total > 0 ? (100 * (d.total - d.free)) / d.total : 0;
        return (
          <div key={d.path} className="disk-row">
            <div className="disk-head">
              <span className="disk-path" title={d.path}>
                <bdi dir="ltr">{d.path}</bdi>
              </span>
              <span className="strong nowrap">{Math.round(used)} %</span>
            </div>
            <div className="progress">
              <div className={`progress-bar ${used >= 90 ? "hot" : "tone-accent"}`} style={{ width: `${used}%` }} />
            </div>
            <div className="muted small">
              {fmtSize(d.free)} frei von {fmtSize(d.total)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ recently added (poster rail)
function RecentlyAddedWidget() {
  const movies = useMovies();
  const series = useSeriesList();
  const now = useNow(60_000);
  if (!movies.data || !series.data) return <Skeleton lines={4} />;
  const items = [
    ...movies.data.map((m) => ({ kind: "movie" as const, id: m.id, title: m.title, year: m.year, poster: m.images?.poster, added: m.added })),
    ...series.data.map((s) => ({ kind: "series" as const, id: s.id, title: s.title, year: s.year, poster: s.images?.poster, added: s.added })),
  ]
    .filter((x) => x.added)
    .sort((a, b) => (parseDate(b.added)?.getTime() ?? 0) - (parseDate(a.added)?.getTime() ?? 0))
    .slice(0, 18);
  if (items.length === 0) return <Empty icon={<Sparkles size={32} />} title="Noch nichts hinzugefügt" />;
  return (
    <div className="poster-rail">
      {items.map((x, i) => (
        <Link key={`${x.kind}-${x.id}`} to={`/${x.kind === "movie" ? "movies" : "series"}/${x.id}`} className="poster-card" title={x.title} style={{ "--i": i } as CSSProperties}>
          <Poster src={x.poster} title={x.title} kind={x.kind} />
          <div className="poster-card-info">
            <div className="poster-card-title">{x.title}</div>
            <div className="poster-card-sub">
              {x.kind === "movie" ? "Film" : "Serie"} · {relTime(x.added, now)}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ recent imports
function RecentWidget() {
  const { data } = useDashboard();
  const now = useNow(30_000);
  if (!data) return <Skeleton lines={5} />;
  if (data.recent.length === 0) return <Empty title="Noch keine Importe" />;
  return (
    <ul className="recent-list widget-scroll">
      {data.recent.map((h) => (
        <li key={h.id}>
          <Link to={h.movie_id ? `/movies/${h.movie_id}` : `/series/${h.series_id}`} className="recent-title" title={h.source_title}>
            {h.source_title}
          </Link>
          <span className="recent-meta">
            <Badge tone={h.event === "upgraded" ? "accent" : "success"}>{HISTORY_EVENT_LABELS[h.event] ?? h.event}</Badge>
            {h.quality && <Badge tone="info">{h.quality}</Badge>}
            <span className="muted small" title={fmtDateTime(h.date)}>
              {relTime(h.date, now)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ indexer quotas
function IndexersWidget() {
  const usage = useQuery({ queryKey: ["indexers-usage"], queryFn: api.indexersUsage, refetchInterval: 60_000 });
  const now = useNow(30_000);
  if (!usage.data) return <Skeleton lines={4} />;
  if (usage.data.length === 0)
    return (
      <Empty icon={<Rss size={32} />} title="Keine Indexer">
        <Link to="/indexers">Indexer hinzufügen</Link>
      </Empty>
    );
  return (
    <div className="usage-list widget-scroll">
      {usage.data.map((u) => {
        const paused = u.paused_until && (parseDate(u.paused_until)?.getTime() ?? 0) > now.getTime();
        return (
          <div key={u.id} className={`usage-card ${!u.enabled ? "disabled" : ""}`}>
            <div className="usage-card-head">
              <Link to={`/indexers/${u.id}`} className="strong">
                {u.name}
              </Link>
              <span className="muted small">{windowLabel(u.limit_mode, u.window_hours)}</span>
              {!u.enabled && <Badge tone="muted">deaktiviert</Badge>}
              {paused && (
                <Badge tone="warning" title={u.last_error ?? undefined}>
                  <PauseCircle size={12} /> pausiert bis {fmtDateTime(u.paused_until)}
                </Badge>
              )}
            </div>
            <div className="usage-pair">
              <UsageMeter st={u.query} now={now} compact />
              <UsageMeter st={u.grab} now={now} compact />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ weekly activity chart
function ActivityChartWidget() {
  const { data } = useQuery({ queryKey: ["stats", 12], queryFn: () => api.stats(12), staleTime: 300_000 });
  if (!data) return <Skeleton lines={5} />;
  const max = Math.max(1, ...data.weeks.map((w) => Math.max(w.grabs, w.imports)));
  return (
    <>
      <div className="week-chart" role="img" aria-label="Grabs und Importe pro Woche">
        {data.weeks.map((w, i) => (
          <div key={w.week} className="week-col" data-tip={`Woche ab ${fmtDate(w.week)}: ${w.grabs} Grabs · ${w.imports} Importe`}>
            <div className="week-bars">
              <span className="week-bar grabs" style={{ height: `${(100 * w.grabs) / max}%`, "--i": i } as CSSProperties} />
              <span className="week-bar imports" style={{ height: `${(100 * w.imports) / max}%`, "--i": i } as CSSProperties} />
            </div>
            <span className="week-label">{fmtDate(w.week).slice(0, 6)}</span>
          </div>
        ))}
      </div>
      <div className="chart-legend">
        <span className="lg-dot lg-grabs">Grabs</span>
        <span className="lg-dot lg-imports">Importe</span>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ registry
export const WIDGETS: WidgetDef[] = [
  { type: "welcome", title: "Begrüßung", description: "Uhrzeit, Tageszusammenfassung und Schnellaktionen", icon: Sparkles, bare: true, sizes: ["l", "xl", "full"], defaultSize: "full", Component: WelcomeWidget },
  { type: "stats", title: "Kennzahlen", description: "Filme, Serien, Fehlende, Speicher und Warteschlange auf einen Blick", icon: LayoutGrid, bare: true, sizes: ["l", "xl", "full"], defaultSize: "full", Component: StatsWidget },
  { type: "upcoming", title: "Demnächst", description: "Releases und Episoden der nächsten 7 Tage", icon: CalendarDays, link: { to: "/calendar", label: "Kalender" }, sizes: ["m", "l", "xl", "full"], defaultSize: "l", Component: UpcomingWidget },
  { type: "downloads", title: "Downloads", description: "Laufende Downloads mit Live-Fortschritt", icon: Download, link: { to: "/activity", label: "Aktivität" }, sizes: ["m", "l", "xl", "full"], defaultSize: "l", Component: DownloadsWidget },
  { type: "recentlyAdded", title: "Neu in der Bibliothek", description: "Zuletzt hinzugefügte Filme und Serien als Poster-Leiste", icon: Sparkles, sizes: ["l", "xl", "full"], defaultSize: "full", Component: RecentlyAddedWidget },
  { type: "library", title: "Vollständigkeit", description: "Wie viel der Bibliothek schon als Datei vorliegt", icon: PieChart, sizes: ["s", "m", "l"], defaultSize: "m", Component: LibraryWidget },
  { type: "disk", title: "Speicherplatz", description: "Belegung der Stammordner", icon: HardDrive, link: { to: "/system/status", label: "Status" }, sizes: ["s", "m", "l", "xl"], defaultSize: "m", Component: DiskWidget },
  { type: "health", title: "Health", description: "Probleme mit Indexern, Clients und Ordnern", icon: HeartPulse, link: { to: "/system/status", label: "System" }, sizes: ["s", "m", "l", "xl"], defaultSize: "m", Component: HealthWidget },
  { type: "activityChart", title: "Aktivität", description: "Grabs und Importe der letzten 12 Wochen", icon: BarChart3, link: { to: "/stats", label: "Statistik" }, sizes: ["m", "l", "xl", "full"], defaultSize: "l", Component: ActivityChartWidget },
  { type: "recent", title: "Zuletzt importiert", description: "Die letzten Importe und Upgrades", icon: Activity, link: { to: "/activity/history", label: "Verlauf" }, sizes: ["m", "l", "xl", "full"], defaultSize: "l", Component: RecentWidget },
  { type: "indexers", title: "Indexer-Kontingente", description: "API- und Grab-Limits deiner Indexer", icon: Rss, link: { to: "/indexers", label: "Indexer" }, sizes: ["m", "l", "xl", "full"], defaultSize: "full", Component: IndexersWidget },
];

export const DEFAULT_LAYOUT: WidgetPlacement[] = WIDGETS.map((w) => ({ type: w.type, size: w.defaultSize }));
