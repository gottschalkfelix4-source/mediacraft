import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Film, Tv, CalendarDays, Activity, SearchX, Rss, Settings, Server, Menu, X, Search, Sun, Moon, LogOut, Wifi, WifiOff,
} from "lucide-react";
import { api } from "../api";
import { useMovies, useSeriesList } from "../hooks";
import { Poster } from "./Media";

interface NavItem {
  to: string;
  label: string;
  icon: typeof Film;
  end?: boolean;
  children?: { to: string; label: string }[];
  badge?: number;
}

export const SETTINGS_NAV = [
  { to: "/settings/media", label: "Medienverwaltung" },
  { to: "/settings/profiles", label: "Profile" },
  { to: "/settings/qualities", label: "Qualitäten" },
  { to: "/settings/customformats", label: "Custom Formats" },
  { to: "/settings/indexers", label: "Indexer-Allgemein" },
  { to: "/settings/downloadclients", label: "Downloadclients" },
  { to: "/settings/metadata", label: "Metadaten" },
  { to: "/settings/notifications", label: "Benachrichtigungen" },
  { to: "/settings/automation", label: "Gesucht / Automatik" },
  { to: "/settings/general", label: "Allgemein / Sicherheit" },
];

export const SYSTEM_NAV = [
  { to: "/system/status", label: "Status" },
  { to: "/system/tasks", label: "Aufgaben" },
  { to: "/system/logs", label: "Logs" },
  { to: "/system/backup", label: "Backup" },
  { to: "/system/recyclebin", label: "Papierkorb" },
  { to: "/system/libraryimport", label: "Bibliotheksimport" },
  { to: "/system/manualimport", label: "Manueller Import" },
];

export function Layout({ children, theme, onToggleTheme, onLogout, connected, authMethod, version }: {
  children: ReactNode;
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onLogout: () => void;
  connected: boolean;
  authMethod: string;
  version?: string;
}) {
  const [drawer, setDrawer] = useState(false);
  const loc = useLocation();
  const { data: queue } = useQuery({ queryKey: ["queue"], queryFn: api.queue, refetchInterval: 30_000 });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 120_000 });
  const activeQueue = (queue ?? []).filter((q) => !["imported", "failed", "removed"].includes(q.status)).length;
  const healthIssues = health?.issues.filter((i) => i.level === "error").length ?? 0;

  useEffect(() => setDrawer(false), [loc.pathname]);

  const nav: NavItem[] = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/movies", label: "Filme", icon: Film, children: [{ to: "/movies/add", label: "Film hinzufügen" }] },
    { to: "/series", label: "Serien", icon: Tv, children: [{ to: "/series/add", label: "Serie hinzufügen" }] },
    { to: "/calendar", label: "Kalender", icon: CalendarDays },
    { to: "/activity", label: "Aktivität", icon: Activity, badge: activeQueue },
    { to: "/wanted", label: "Gesucht", icon: SearchX },
    { to: "/indexers", label: "Indexer", icon: Rss },
    { to: "/settings", label: "Einstellungen", icon: Settings, children: SETTINGS_NAV },
    { to: "/system", label: "System", icon: Server, children: SYSTEM_NAV, badge: healthIssues || undefined },
  ];

  return (
    <div className={`app ${drawer ? "drawer-open" : ""}`}>
      <aside className="sidebar" aria-label="Hauptnavigation">
        <div className="brand">
          <div className="brand-logo">M</div>
          <div className="brand-text">
            MediaCraft
            {version && <span className="brand-ver">v{version}</span>}
          </div>
          <button className="icon-btn drawer-close" onClick={() => setDrawer(false)} aria-label="Menü schließen" title="Menü schließen">
            <X size={20} />
          </button>
        </div>
        <nav className="nav">
          {nav.map((n) => {
            const active = n.end ? loc.pathname === n.to : loc.pathname === n.to || loc.pathname.startsWith(n.to + "/");
            return (
              <div key={n.to} className={`nav-group ${active ? "active" : ""}`}>
                <NavLink to={n.children && n.to !== "/movies" && n.to !== "/series" ? n.children[0].to : n.to} end={n.end} className={() => `nav-link ${active ? "active" : ""}`}>
                  <n.icon size={18} />
                  <span>{n.label}</span>
                  {n.badge ? <span className="nav-badge">{n.badge}</span> : null}
                </NavLink>
                {n.children && active && (
                  <div className="nav-sub">
                    {n.children.map((c) => (
                      <NavLink key={c.to} to={c.to} className={({ isActive }) => `nav-sublink ${isActive ? "active" : ""}`}>
                        {c.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className={`conn ${connected ? "on" : "off"}`} title={connected ? "Live-Verbindung aktiv" : "Live-Verbindung getrennt"}>
            {connected ? <Wifi size={14} /> : <WifiOff size={14} />} {connected ? "Live" : "Offline"}
          </span>
        </div>
      </aside>
      <div className="drawer-backdrop" onClick={() => setDrawer(false)} />
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setDrawer(true)} aria-label="Menü öffnen" title="Menü">
            <Menu size={22} />
          </button>
          <GlobalSearch />
          <div className="topbar-actions">
            <button className="icon-btn" onClick={onToggleTheme} title={theme === "dark" ? "Helles Design" : "Dunkles Design"} aria-label="Design umschalten">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            {authMethod === "forms" && (
              <button className="icon-btn" onClick={onLogout} title="Abmelden" aria-label="Abmelden">
                <LogOut size={18} />
              </button>
            )}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const { data: movies } = useMovies();
  const { data: series } = useSeriesList();
  const nav = useNavigate();
  const ref = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return [];
    const match = (t: string, o: string | null, alts: string[]) =>
      t.toLowerCase().includes(term) || (o ?? "").toLowerCase().includes(term) || alts.some((a) => a.toLowerCase().includes(term));
    const m = (movies ?? []).filter((x) => match(x.title, x.original_title, x.alt_titles ?? [])).map((x) => ({ kind: "movie" as const, id: x.id, title: x.title, year: x.year, poster: x.images?.poster }));
    const s = (series ?? []).filter((x) => match(x.title, x.original_title, x.alt_titles ?? [])).map((x) => ({ kind: "series" as const, id: x.id, title: x.title, year: x.year, poster: x.images?.poster }));
    const all = [...m, ...s];
    all.sort((a, b) => {
      const as = a.title.toLowerCase().startsWith(term) ? 0 : 1;
      const bs = b.title.toLowerCase().startsWith(term) ? 0 : 1;
      return as - bs || a.title.localeCompare(b.title, "de");
    });
    return all.slice(0, 10);
  }, [q, movies, series]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement))) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (r: (typeof results)[number]) => {
    nav(r.kind === "movie" ? `/movies/${r.id}` : `/series/${r.id}`);
    setQ("");
    setOpen(false);
    ref.current?.blur();
  };

  return (
    <div className="global-search">
      <Search size={16} className="gs-icon" />
      <input
        ref={ref}
        className="gs-input"
        placeholder="Bibliothek durchsuchen… ( / )"
        value={q}
        aria-label="Bibliothek durchsuchen"
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setSel(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setSel((s) => Math.min(s + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setSel((s) => Math.max(s - 1, 0));
          } else if (e.key === "Enter" && results[sel]) {
            go(results[sel]);
          } else if (e.key === "Escape") {
            setQ("");
            ref.current?.blur();
          }
        }}
      />
      {open && q.trim() && (
        <div className="gs-results" role="listbox">
          {results.length === 0 && <div className="gs-empty">Nichts in der Bibliothek gefunden</div>}
          {results.map((r, i) => (
            <button key={`${r.kind}-${r.id}`} className={`gs-item ${i === sel ? "sel" : ""}`} onMouseDown={(e) => e.preventDefault()} onClick={() => go(r)} role="option" aria-selected={i === sel}>
              <Poster src={r.poster} title={r.title} kind={r.kind} className="poster-xs" />
              <span className="gs-title">
                {r.title} {r.year ? <span className="muted">({r.year})</span> : null}
              </span>
              <span className="gs-kind">{r.kind === "movie" ? <Film size={13} /> : <Tv size={13} />}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
