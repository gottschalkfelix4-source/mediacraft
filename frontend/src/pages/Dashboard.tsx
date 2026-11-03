import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Film, Tv, ListVideo, SearchX, HardDrive, Download, AlertTriangle, CheckCircle2, Info, PauseCircle, Rss } from "lucide-react";
import { api } from "../api";
import { Card, ErrorBox, Loading, PageHeader, Empty, Badge } from "../components/ui";
import { Poster } from "../components/Media";
import { UsageMeter, windowLabel } from "../components/Usage";
import { epCode, fmtDateTime, fmtNumber, fmtSize, HISTORY_EVENT_LABELS, relTime, WEEKDAYS, parseDate, fmtTime } from "../format";
import { useNow } from "../hooks";
import type { CalendarItem } from "../types";

export function Dashboard() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 60_000 });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const usage = useQuery({ queryKey: ["indexers-usage"], queryFn: api.indexersUsage, refetchInterval: 60_000 });
  const disk = useQuery({ queryKey: ["diskspace"], queryFn: api.diskspace, staleTime: 300_000 });
  const now = useNow(30_000);

  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;

  const stats = [
    { icon: Film, label: "Filme", value: fmtNumber(data.movies.total), sub: `${fmtNumber(data.movies.with_file)} vorhanden`, to: "/movies" },
    { icon: Tv, label: "Serien", value: fmtNumber(data.series.total), sub: `${fmtNumber(data.series.episodes)} Episoden`, to: "/series" },
    { icon: ListVideo, label: "Episoden-Dateien", value: fmtNumber(data.series.episode_files), sub: `von ${fmtNumber(data.series.episodes)}`, to: "/series" },
    { icon: SearchX, label: "Fehlend", value: fmtNumber(data.movies.missing + data.series.missing), sub: `${data.movies.missing} Filme · ${data.series.missing} Episoden`, to: "/wanted", tone: data.movies.missing + data.series.missing > 0 ? "warning" : undefined },
    { icon: HardDrive, label: "Belegt", value: fmtSize(data.size_on_disk), sub: disk.data?.length ? `${fmtSize(disk.data.reduce((a, d) => a + d.free, 0))} frei` : "Größe auf Disk", to: "/system/status" },
    { icon: Download, label: "Warteschlange", value: fmtNumber(data.queue), sub: "aktive Downloads", to: "/activity", tone: data.queue ? "accent" : undefined },
  ];

  const issues = health.data?.issues ?? [];

  return (
    <div className="page">
      <PageHeader title="Dashboard" />
      <div className="stat-grid">
        {stats.map((s) => (
          <Link key={s.label} to={s.to} className={`stat ${s.tone ? `stat-${s.tone}` : ""}`}>
            <s.icon size={22} className="stat-icon" />
            <div>
              <div className="stat-value">{s.value}</div>
              <div className="stat-label">{s.label}</div>
              <div className="stat-sub">{s.sub}</div>
            </div>
          </Link>
        ))}
      </div>

      <div className="dash-grid">
        <Card title="Demnächst" actions={<Link to="/calendar" className="btn btn-sm">Kalender</Link>} className="dash-upcoming">
          {data.upcoming.length === 0 ? <Empty title="Nichts in den nächsten 7 Tagen" /> : <UpcomingList items={data.upcoming} now={now} />}
        </Card>

        <Card title="Health" actions={<Link to="/system/status" className="btn btn-sm">System</Link>}>
          {health.isLoading ? (
            <Loading />
          ) : issues.length === 0 ? (
            <div className="health-ok">
              <CheckCircle2 size={20} /> Keine Probleme gefunden
            </div>
          ) : (
            <ul className="issue-list">
              {issues.map((i, n) => (
                <li key={n} className={`issue issue-${i.level}`}>
                  {i.level === "error" ? <AlertTriangle size={16} /> : i.level === "warning" ? <AlertTriangle size={16} /> : <Info size={16} />}
                  <span>{i.message}</span>
                  <Badge tone="muted">{i.source}</Badge>
                </li>
              ))}
            </ul>
          )}
          {health.data?.checked && <div className="muted small mt-sm">Geprüft {relTime(health.data.checked, now)}</div>}
        </Card>

        <Card title="Indexer-Kontingente" actions={<Link to="/indexers" className="btn btn-sm">Indexer</Link>}>
          {usage.isLoading && <Loading />}
          {usage.data?.length === 0 && (
            <Empty icon={<Rss size={32} />} title="Keine Indexer">
              <Link to="/indexers">Indexer hinzufügen</Link>
            </Empty>
          )}
          <div className="usage-list">
            {usage.data?.map((u) => {
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
        </Card>

        <Card title="Zuletzt importiert" actions={<Link to="/activity/history" className="btn btn-sm">Verlauf</Link>}>
          {data.recent.length === 0 ? (
            <Empty title="Noch keine Importe" />
          ) : (
            <ul className="recent-list">
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
          )}
        </Card>
      </div>
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
                    <div>{WEEKDAYS[d.getDay()]} {String(d.getDate()).padStart(2, "0")}.{String(d.getMonth() + 1).padStart(2, "0")}.</div>
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
