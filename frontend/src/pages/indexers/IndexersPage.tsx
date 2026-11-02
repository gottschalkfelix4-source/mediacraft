import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, BarChart3, PlayCircle, PauseCircle, Rss, Search, UserSearch, Magnet, Newspaper, AlertTriangle, PlugZap, Globe } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Loading, PageHeader } from "../../components/ui";
import { useConfirm } from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { UsageMeter, windowLabel } from "../../components/Usage";
import { useApiMutation, useCommand, useNow } from "../../hooks";
import { fmtDateTime, parseDate, relTime } from "../../format";
import { IndexerDialog } from "./IndexerDialog";
import type { Indexer } from "../../types";

export function IndexersPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["indexers"], queryFn: api.indexers, refetchInterval: 60_000 });
  const [editing, setEditing] = useState<Indexer | "new" | null>(null);
  const now = useNow(30_000);
  const command = useCommand();

  return (
    <div className="page">
      <PageHeader title="Indexer" sub="Newznab/Torznab-Indexer mit Query- und Grab-Kontingenten">
        <button className="btn" onClick={() => command("rss_sync")} title="RSS-Sync jetzt starten">
          <Rss size={15} /> RSS-Sync
        </button>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>
          <Plus size={16} /> Indexer hinzufügen
        </button>
      </PageHeader>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && (
        <Empty icon={<Rss size={36} />} title="Noch keine Indexer">
          <p>Füge einen Newznab- (Usenet) oder Torznab-Indexer (Torrent) hinzu – oder synchronisiere ihn über Prowlarr (Sonarr-/Radarr-App mit der MediaCraft-URL).</p>
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            <Plus size={16} /> Indexer hinzufügen
          </button>
        </Empty>
      )}
      <div className="indexer-list">
        {data?.map((i) => (
          <IndexerCard key={i.id} i={i} now={now} onEdit={() => setEditing(i)} />
        ))}
      </div>
      {editing && <IndexerDialog indexer={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function IndexerCard({ i, now, onEdit }: { i: Indexer; now: Date; onEdit: () => void }) {
  const confirm = useConfirm();
  const toast = useToast();
  const paused = !!i.disabled_until && (parseDate(i.disabled_until)?.getTime() ?? 0) > now.getTime();
  const unpause = useApiMutation(() => api.unpauseIndexer(i.id), { invalidate: [["indexers"], ["indexers-usage"], ["health"]], success: `${i.name} wieder aktiv` });
  const toggle = useApiMutation((v: boolean) => api.updateIndexer(i.id, { enabled: v }), { invalidate: [["indexers"], ["indexers-usage"]] });
  const del = useApiMutation(() => api.deleteIndexer(i.id), { invalidate: [["indexers"], ["indexers-usage"]], success: `${i.name} gelöscht` });
  const [testing, setTesting] = useState(false);

  const test = async () => {
    setTesting(true);
    try {
      await api.testIndexer({ id: i.id });
      toast.success(`${i.name}: Test erfolgreich`, "Capabilities wurden abgerufen");
    } catch (e) {
      toast.error(`${i.name}: Test fehlgeschlagen`, errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  const rl = i.remote_limits ?? {};
  const hasRemote = i.sync_remote_limits && rl.seen && (rl.api_max != null || rl.grab_max != null || rl.api_current != null || rl.grab_current != null);

  return (
    <div className={`indexer-card ${!i.enabled ? "disabled" : ""} ${paused ? "paused" : ""}`}>
      <div className="indexer-head">
        <div className="indexer-title">
          {i.protocol === "torrent" ? <Magnet size={18} className="proto-torrent" /> : <Newspaper size={18} className="proto-usenet" />}
          <h3>{i.name}</h3>
          <Badge tone={i.protocol === "torrent" ? "warning" : "info"}>{i.protocol === "torrent" ? "Torznab" : "Newznab"}</Badge>
          <Badge tone="muted" title="Priorität (kleiner = bevorzugt)">Prio {i.priority}</Badge>
          {!i.enabled && <Badge tone="muted">deaktiviert</Badge>}
          {paused && (
            <Badge tone="warning" title={i.last_error ?? undefined}>
              <PauseCircle size={12} /> pausiert bis {fmtDateTime(i.disabled_until)} ({relTime(i.disabled_until, now)})
            </Badge>
          )}
          {i.sync_source && Object.keys(i.sync_source).length > 0 && <Badge tone="accent" title="Per Prowlarr synchronisiert">Prowlarr</Badge>}
        </div>
        <div className="indexer-actions">
          <label className="toggle" title={i.enabled ? "Aktiv" : "Deaktiviert"}>
            <input type="checkbox" checked={i.enabled} onChange={(e) => toggle.mutate(e.target.checked)} aria-label="Aktiv" />
            <span className="toggle-track"><span className="toggle-thumb" /></span>
          </label>
          {paused && (
            <button className="btn btn-sm" onClick={() => unpause.mutate(undefined)} title="Pause aufheben">
              <PlayCircle size={14} /> Fortsetzen
            </button>
          )}
          <button className="icon-btn" onClick={test} disabled={testing} title="Testen (Caps abrufen – zählt als Query)" aria-label="Testen">
            <PlugZap size={16} className={testing ? "spin" : ""} />
          </button>
          <Link className="icon-btn" to={`/indexers/${i.id}`} title="Nutzungsstatistik" aria-label="Nutzungsstatistik">
            <BarChart3 size={16} />
          </Link>
          <button className="icon-btn" onClick={onEdit} title="Bearbeiten" aria-label="Bearbeiten">
            <Pencil size={16} />
          </button>
          <button
            className="icon-btn danger"
            title="Löschen"
            aria-label="Löschen"
            onClick={async () => {
              if (await confirm({ title: "Indexer löschen?", message: `„${i.name}“ und seine Nutzungsdaten werden gelöscht.`, confirmLabel: "Löschen", danger: true })) del.mutate(undefined);
            }}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      <div className="indexer-sub">
        <span className="mono small break">{i.url}</span>
        <span className="feature-flags">
          <span className={i.enable_rss ? "on" : "off"} title="RSS"><Rss size={13} /> RSS</span>
          <span className={i.enable_auto_search ? "on" : "off"} title="Automatische Suche"><Search size={13} /> Auto</span>
          <span className={i.enable_interactive_search ? "on" : "off"} title="Interaktive Suche"><UserSearch size={13} /> Interaktiv</span>
        </span>
        <span className="muted small">{windowLabel(i.limit_mode, i.limit_window_hours, i.limit_reset_hour)}</span>
        {i.min_request_interval > 0 && <span className="muted small">min. {i.min_request_interval} s Abstand</span>}
      </div>
      {i.last_error && (
        <div className={`alert ${paused ? "alert-warning" : "alert-muted"} alert-compact`}>
          <AlertTriangle size={14} /> <span className="break">{i.last_error}</span>
          {i.failure_count > 0 && <span className="muted small"> · {i.failure_count} Fehler in Folge</span>}
        </div>
      )}
      {i.usage && (
        <div className="usage-pair">
          <UsageMeter st={i.usage.query} now={now} />
          <UsageMeter st={i.usage.grab} now={now} />
        </div>
      )}
      {hasRemote && (
        <div className="remote-limits small">
          <Globe size={13} /> Vom Indexer gemeldet (apilimits, {relTime(rl.seen, now)}):{" "}
          <span>API {rl.api_current ?? "?"}/{rl.api_max ?? "?"}</span> · <span>Grabs {rl.grab_current ?? "?"}/{rl.grab_max ?? "?"}</span>
        </div>
      )}
    </div>
  );
}
