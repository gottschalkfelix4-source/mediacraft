import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, CalendarCheck, Rss, Film, Tv, Copy } from "lucide-react";
import { api, API_BASE } from "../api";
import { ErrorBox, PageHeader, Toggle, Spinner } from "../components/ui";
import { useToast } from "../components/Toast";
import { useNow, useSettings, useStored } from "../hooks";
import { epCode, fmtTime, isoLocalDay, MONTHS, parseDate, toUtcNaive, WEEKDAYS, WEEKDAYS_LONG } from "../format";
import type { CalendarItem } from "../types";

type ViewKind = "week" | "month";

function startOfWeek(d: Date, firstDay: number): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (x.getDay() - firstDay + 7) % 7;
  x.setDate(x.getDate() - diff);
  return x;
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

export function CalendarPage() {
  const [view, setView] = useStored<ViewKind>("mc-cal-view", "week");
  const [unmonitored, setUnmonitored] = useStored("mc-cal-unmon", false);
  const [anchor, setAnchor] = useState(() => new Date());
  const settings = useSettings();
  const firstDay = settings.data?.ui?.first_day_of_week ?? 1;
  const now = useNow(60_000);
  const toast = useToast();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status, staleTime: 300_000 });

  const { start, end, days } = useMemo(() => {
    if (view === "week") {
      const s = startOfWeek(anchor, firstDay);
      return { start: s, end: addDays(s, 7), days: Array.from({ length: 7 }, (_, i) => addDays(s, i)) };
    }
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const s = startOfWeek(first, firstDay);
    const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    const e = addDays(startOfWeek(last, firstDay), 7);
    const n = Math.round((e.getTime() - s.getTime()) / 86400000);
    return { start: s, end: e, days: Array.from({ length: n }, (_, i) => addDays(s, i)) };
  }, [view, anchor, firstDay]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["calendar", toUtcNaive(start), toUtcNaive(end), unmonitored],
    queryFn: () => api.calendar(toUtcNaive(start), toUtcNaive(end), unmonitored),
  });

  const byDay = useMemo(() => {
    const m = new Map<string, CalendarItem[]>();
    for (const it of data ?? []) {
      const d = parseDate(it.date);
      if (!d) continue;
      const k = isoLocalDay(d);
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(it);
    }
    return m;
  }, [data]);

  const move = (dir: number) => {
    const x = new Date(anchor);
    if (view === "week") x.setDate(x.getDate() + 7 * dir);
    else x.setMonth(x.getMonth() + dir, 1);
    setAnchor(x);
  };

  const title =
    view === "month"
      ? `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`
      : `${String(days[0].getDate()).padStart(2, "0")}.${String(days[0].getMonth() + 1).padStart(2, "0")}. – ${String(days[6].getDate()).padStart(2, "0")}.${String(days[6].getMonth() + 1).padStart(2, "0")}.${days[6].getFullYear()}`;

  const feedUrl = `${window.location.origin}${API_BASE}/feed/calendar.ics${status.data?.api_key ? `?apikey=${status.data.api_key}` : ""}`;
  const today = isoLocalDay(now);
  const weekdayHeads = Array.from({ length: 7 }, (_, i) => WEEKDAYS[(firstDay + i) % 7]);

  return (
    <div className="page">
      <PageHeader title="Kalender">
        <a className="btn" href={`${API_BASE}/feed/calendar.ics`} target="_blank" rel="noreferrer" title="iCal-Feed öffnen">
          <Rss size={15} /> iCal
        </a>
        <button
          className="btn"
          title="iCal-URL inkl. API-Key kopieren (für Kalender-Apps)"
          onClick={() => {
            navigator.clipboard?.writeText(feedUrl).then(
              () => toast.success("iCal-URL kopiert"),
              () => toast.error("Kopieren nicht möglich", feedUrl),
            );
          }}
        >
          <Copy size={15} /> URL kopieren
        </button>
      </PageHeader>
      <div className="toolbar">
        <div className="seg">
          <button className="seg-btn" onClick={() => move(-1)} title="Zurück" aria-label="Zurück">
            <ChevronLeft size={16} />
          </button>
          <button className="seg-btn" onClick={() => setAnchor(new Date())} title="Heute">
            <CalendarCheck size={15} /> Heute
          </button>
          <button className="seg-btn" onClick={() => move(1)} title="Weiter" aria-label="Weiter">
            <ChevronRight size={16} />
          </button>
        </div>
        <h2 className="cal-title">{title}</h2>
        {isLoading && <Spinner />}
        <div className="seg ml-auto">
          <button className={`seg-btn ${view === "week" ? "active" : ""}`} onClick={() => setView("week")}>
            Woche
          </button>
          <button className={`seg-btn ${view === "month" ? "active" : ""}`} onClick={() => setView("month")}>
            Monat
          </button>
        </div>
        <Toggle checked={unmonitored} onChange={setUnmonitored} label="Nicht überwachte zeigen" />
      </div>
      <div className="cal-legend">
        <span className="lg lg-has-file">Vorhanden</span>
        <span className="lg lg-missing">Fehlt</span>
        <span className="lg lg-upcoming">Demnächst</span>
        <span className="lg lg-unmonitored">Nicht überwacht</span>
      </div>
      {error ? <ErrorBox error={error} /> : null}
      {view === "week" ? (
        <div className="cal-week">
          {days.map((d) => {
            const k = isoLocalDay(d);
            const items = byDay.get(k) ?? [];
            return (
              <div key={k} className={`cal-day ${k === today ? "today" : ""}`}>
                <div className="cal-day-head">
                  <span>{WEEKDAYS_LONG[d.getDay()]}</span>
                  <span className="muted">
                    {String(d.getDate()).padStart(2, "0")}.{String(d.getMonth() + 1).padStart(2, "0")}.
                  </span>
                </div>
                <div className="cal-day-body">
                  {items.length === 0 && <div className="muted small cal-none">–</div>}
                  {items.map((it) => (
                    <CalEntry key={`${it.type}-${it.id}-${it.release_type ?? ""}`} it={it} now={now} full />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="cal-month">
          {weekdayHeads.map((w) => (
            <div key={w} className="cal-month-head">
              {w}
            </div>
          ))}
          {days.map((d) => {
            const k = isoLocalDay(d);
            const items = byDay.get(k) ?? [];
            const other = d.getMonth() !== anchor.getMonth();
            return (
              <div key={k} className={`cal-cell ${k === today ? "today" : ""} ${other ? "other" : ""}`}>
                <div className="cal-cell-num">{d.getDate()}</div>
                {items.slice(0, 5).map((it) => (
                  <CalEntry key={`${it.type}-${it.id}-${it.release_type ?? ""}`} it={it} now={now} />
                ))}
                {items.length > 5 && <div className="muted small">+{items.length - 5} weitere</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CalEntry({ it, now, full }: { it: CalendarItem; now: Date; full?: boolean }) {
  const d = parseDate(it.date);
  const past = d ? d.getTime() <= now.getTime() : false;
  const state = !it.monitored ? "unmonitored" : it.has_file ? "has-file" : past ? "missing" : "upcoming";
  const to = it.type === "movie" ? `/movies/${it.id}` : `/series/${it.series_id}`;
  const rt = it.release_type === "cinema" ? "Kino" : it.release_type === "digital" ? "Digital" : it.release_type === "physical" ? "Disc" : "";
  const tip = it.type === "episode" ? `${it.title} ${epCode(it.season, it.number)} – ${it.episode_title ?? ""}\n${fmtTime(d)}${it.network ? ` · ${it.network}` : ""}` : `${it.title} (${it.year ?? ""}) – ${rt}`;
  return (
    <Link to={to} className={`cal-entry state-${state}`} title={tip}>
      <span className="cal-entry-title">
        {it.type === "movie" ? <Film size={11} /> : <Tv size={11} />} {it.title}
      </span>
      {it.type === "episode" ? (
        <span className="cal-entry-sub">
          {epCode(it.season, it.number)}
          {full && it.episode_title ? ` · ${it.episode_title}` : ""}
          {full && <span className="cal-entry-time"> {fmtTime(d)}</span>}
        </span>
      ) : (
        <span className="cal-entry-sub">{rt}</span>
      )}
    </Link>
  );
}
