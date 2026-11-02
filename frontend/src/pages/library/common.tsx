import type { ReactNode } from "react";
import { LayoutGrid, List, Search } from "lucide-react";
import { Select } from "../../components/ui";
import type { QualityProfile, RootFolder } from "../../types";

export type ViewMode = "grid" | "table";
export type FilterMode = "all" | "monitored" | "missing" | "have";
export type SortMode = "title" | "year" | "added";

export function LibraryToolbar({ view, setView, filter, setFilter, sort, setSort, search, setSearch, count, children }: {
  view: ViewMode;
  setView: (v: ViewMode) => void;
  filter: FilterMode;
  setFilter: (v: FilterMode) => void;
  sort: SortMode;
  setSort: (v: SortMode) => void;
  search: string;
  setSearch: (v: string) => void;
  count: number;
  children?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <div className="search-box">
        <Search size={15} />
        <input className="input" placeholder="Filtern…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Titel filtern" />
      </div>
      <div className="seg" role="group" aria-label="Filter">
        {(
          [
            ["all", "Alle"],
            ["monitored", "Überwacht"],
            ["missing", "Fehlend"],
            ["have", "Vorhanden"],
          ] as [FilterMode, string][]
        ).map(([k, l]) => (
          <button key={k} className={`seg-btn ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)}>
            {l}
          </button>
        ))}
      </div>
      <Select<SortMode>
        value={sort}
        onValue={setSort}
        aria-label="Sortierung"
        options={[
          { value: "title", label: "Sortieren: Titel" },
          { value: "year", label: "Sortieren: Jahr" },
          { value: "added", label: "Sortieren: Hinzugefügt" },
        ]}
      />
      <div className="seg" role="group" aria-label="Ansicht">
        <button className={`seg-btn ${view === "grid" ? "active" : ""}`} onClick={() => setView("grid")} title="Posteransicht" aria-label="Posteransicht">
          <LayoutGrid size={16} />
        </button>
        <button className={`seg-btn ${view === "table" ? "active" : ""}`} onClick={() => setView("table")} title="Tabellenansicht" aria-label="Tabellenansicht">
          <List size={16} />
        </button>
      </div>
      <span className="muted">{count} Einträge</span>
      {children}
    </div>
  );
}

export function rootFolderOptions(folders: RootFolder[], types: string[]) {
  return folders.filter((f) => types.includes(f.media_type)).map((f) => ({ value: f.path, label: f.path }));
}

export function profileOptions(profiles: QualityProfile[]) {
  return profiles.map((p) => ({ value: p.id, label: p.name }));
}

export function textMatch(term: string, ...titles: (string | null | undefined)[]): boolean {
  if (!term) return true;
  const t = term.toLowerCase();
  return titles.some((x) => (x ?? "").toLowerCase().includes(t));
}
