import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, RotateCcw, XOctagon, AlertTriangle, Download, Magnet, Newspaper, RefreshCw, X } from "lucide-react";
import { api, errorMessage } from "../api";
import { Badge, Empty, ErrorBox, Loading, PageHeader, Pager, Progress, Select, Spinner, Tabs } from "../components/ui";
import { Modal, useConfirm } from "../components/Modal";
import { useToast } from "../components/Toast";
import { SelectAllBox, useSelection } from "../components/MassEditor";
import { useApiMutation, useCommand } from "../hooks";
import { useEventListener } from "../events";
import { fmtDateTime, fmtDuration, fmtSize, HISTORY_EVENT_LABELS, langLabel, QUEUE_STATUS_LABELS } from "../format";
import { HistoryTable } from "./library/HistoryTable";
import type { QueueItem } from "../types";

type TabKey = "queue" | "pending" | "history" | "blocklist";

export function ActivityPage() {
  const params = useParams();
  const tab = (["queue", "pending", "history", "blocklist"].includes(params.tab ?? "") ? params.tab : "queue") as TabKey;
  const nav = useNavigate();
  const command = useCommand();
  const queue = useQuery({ queryKey: ["queue"], queryFn: api.queue, refetchInterval: 5000 });
  const pending = useQuery({ queryKey: ["pending"], queryFn: api.pending, refetchInterval: 30_000 });
  const qc = useQueryClient();
  useEventListener((m) => {
    if (m.type === "queue.updated") qc.invalidateQueries({ queryKey: ["queue"] });
  });

  return (
    <div className="page">
      <PageHeader title="Aktivität">
        <button className="btn" onClick={() => command("check_downloads")} title="Downloadclients jetzt abfragen">
          <RefreshCw size={15} /> Downloads prüfen
        </button>
        <button className="btn" onClick={() => command("rss_sync")} title="RSS-Sync starten">
          <Download size={15} /> RSS-Sync
        </button>
      </PageHeader>
      <Tabs
        tabs={[
          { key: "queue", label: "Warteschlange", count: queue.data?.length },
          { key: "pending", label: "Zurückgestellt", count: pending.data?.length || undefined },
          { key: "history", label: "Verlauf" },
          { key: "blocklist", label: "Blocklist" },
        ]}
        active={tab}
        onChange={(k) => nav(`/activity/${k}`)}
      />
      {tab === "queue" && <QueueTab items={queue.data} loading={queue.isLoading} error={queue.error} />}
      {tab === "pending" && <PendingTab />}
      {tab === "history" && <HistoryTab />}
      {tab === "blocklist" && <BlocklistTab />}
    </div>
  );
}

const STATUS_TONE: Record<string, "success" | "info" | "accent" | "danger" | "muted" | "warning"> = {
  downloading: "accent",
  queued: "muted",
  grabbed: "info",
  paused: "muted",
  completed: "success",
  importing: "info",
  imported: "success",
  failed: "danger",
  import_blocked: "warning",
  warning: "warning",
};

/** Row selection that ignores rows which no longer exist (lists refresh in the background). */
function useRowSelection(rowIds: number[]) {
  const sel = useSelection();
  const present = new Set(rowIds);
  const ids = new Set([...sel.ids].filter((id) => present.has(id)));
  return { ...sel, ids, list: [...ids], allIds: rowIds };
}
type RowSel = ReturnType<typeof useRowSelection>;

function SelectHead({ sel }: { sel: RowSel }) {
  return (
    <th className="w-check">
      <SelectAllBox all={sel.allIds} selected={sel.ids} onChange={(on) => sel.setAll(sel.allIds, on)} />
    </th>
  );
}

function SelectCell({ sel, id }: { sel: RowSel; id: number }) {
  return (
    <td>
      <input type="checkbox" aria-label="Eintrag auswählen" checked={sel.ids.has(id)} onChange={() => sel.toggle(id)} />
    </td>
  );
}

function BulkBar({ sel, children }: { sel: RowSel; children: ReactNode }) {
  if (sel.list.length === 0) return null;
  return (
    <div className="save-bar dirty selection-bar">
      <span className="strong">{sel.list.length} ausgewählt</span>
      <span className="grow" />
      {children}
      <button className="icon-btn" onClick={sel.clear} title="Auswahl aufheben" aria-label="Auswahl aufheben">
        <X size={16} />
      </button>
    </div>
  );
}

function QueueTab({ items, loading, error }: { items?: QueueItem[]; loading: boolean; error: unknown }) {
  const [removing, setRemoving] = useState<QueueItem[] | null>(null);
  const sel = useRowSelection(items?.map((q) => q.id) ?? []);
  const qc = useQueryClient();
  const toast = useToast();
  const retry = async (q: QueueItem) => {
    try {
      const r = await api.retryQueueImport(q.id);
      if (r.queued) toast.success("Import eingeplant", `${q.title}
Startet, sobald kein anderer Import läuft.`);
      else if (r.ok) toast.success("Import erfolgreich", q.title);
      else toast.warning("Import nicht möglich", r.messages?.join("\n"));
      qc.invalidateQueries({ queryKey: ["queue"] });
    } catch (e) {
      toast.error("Import fehlgeschlagen", errorMessage(e));
    }
  };

  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!items?.length) return <Empty icon={<Download size={36} />} title="Die Warteschlange ist leer" />;
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <SelectHead sel={sel} />
              <th>Status</th>
              <th>Titel</th>
              <th>Medium</th>
              <th>Qualität</th>
              <th>Client / Indexer</th>
              <th className="w-progress">Fortschritt</th>
              <th className="num">Restzeit</th>
              <th className="w-actions" />
            </tr>
          </thead>
          <tbody>
            {items.map((q) => {
              const pct = Math.round(q.progress ?? 0); // 0..100
              const problem = ["import_blocked", "warning", "failed"].includes(q.status);
              return (
                <tr key={q.id} className={sel.ids.has(q.id) ? "row-selected" : problem ? "row-warn" : ""}>
                  <SelectCell sel={sel} id={q.id} />
                  <td>
                    <Badge tone={STATUS_TONE[q.status] ?? "default"} title={q.client_status ?? undefined}>
                      {QUEUE_STATUS_LABELS[q.status] ?? q.status}
                    </Badge>
                  </td>
                  <td className="break">
                    <div className="small">
                      {q.protocol === "torrent" ? <Magnet size={12} className="muted" /> : <Newspaper size={12} className="muted" />} {q.title}
                    </div>
                    {q.messages?.length > 0 && (
                      <ul className="queue-msgs">
                        {q.messages.map((m, i) => (
                          <li key={i}>
                            <AlertTriangle size={12} /> {m}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    {q.target ? (
                      <Link to={q.target.type === "movie" ? `/movies/${q.target.id}` : `/series/${q.target.id}`}>
                        {q.target.title}
                        {q.target.year ? ` (${q.target.year})` : ""}
                      </Link>
                    ) : (
                      "–"
                    )}
                    {q.episode_ids?.length > 0 && <div className="muted small">{q.episode_ids.length} Episode(n)</div>}
                  </td>
                  <td>
                    <Badge tone="info">{q.quality}</Badge>
                    {q.languages?.length > 0 && <div className="muted small">{q.languages.map(langLabel).join(", ")}</div>}
                  </td>
                  <td className="small">
                    {q.download_client ?? "–"}
                    <div className="muted">{q.indexer ?? ""}</div>
                  </td>
                  <td>
                    <div className="progress-labeled">
                      <Progress value={pct} tone={problem ? "warning" : pct >= 100 ? "success" : "accent"} />
                      <span>{pct} %</span>
                    </div>
                    <div className="muted small">
                      {fmtSize(q.size - q.size_left)} / {fmtSize(q.size)}
                    </div>
                  </td>
                  <td className="num nowrap">{q.eta_seconds ? fmtDuration(q.eta_seconds) : "–"}</td>
                  <td className="actions">
                    {["completed", "import_blocked", "warning"].includes(q.status) && (
                      <button className="icon-btn" title="Import erneut versuchen" aria-label="Import erneut versuchen" onClick={() => retry(q)}>
                        <RotateCcw size={15} />
                      </button>
                    )}
                    <button className="icon-btn danger" title="Entfernen" aria-label="Entfernen" onClick={() => setRemoving([q])}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <BulkBar sel={sel}>
        <button className="btn btn-danger-outline" onClick={() => setRemoving(items.filter((q) => sel.ids.has(q.id)))}>
          <Trash2 size={15} /> Entfernen
        </button>
      </BulkBar>
      {removing && (
        <RemoveQueueDialog
          items={removing}
          onClose={() => setRemoving(null)}
          onDone={() => {
            for (const q of removing) if (sel.ids.has(q.id)) sel.toggle(q.id);
          }}
        />
      )}
    </>
  );
}

function RemoveQueueDialog({ items, onClose, onDone }: { items: QueueItem[]; onClose: () => void; onDone: () => void }) {
  const [fromClient, setFromClient] = useState(true);
  const [blocklist, setBlocklist] = useState(false);
  const [searchAgain, setSearchAgain] = useState(false);
  const opts = { remove_from_client: fromClient, blocklist, search_again: blocklist && searchAgain };
  const rm = useApiMutation(() => api.bulkRemoveQueue(items.map((q) => q.id), opts), {
    invalidate: [["queue"], ["blocklist"]],
    success: (r) => (r.deleted === 1 ? "Aus der Warteschlange entfernt" : `${r.deleted} Einträge aus der Warteschlange entfernt`),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  return (
    <Modal
      title={items.length === 1 ? "Aus Warteschlange entfernen" : `${items.length} Einträge aus Warteschlange entfernen`}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-danger" onClick={() => rm.mutate(undefined)} disabled={rm.isPending}>
            {rm.isPending ? <Spinner size={14} /> : <Trash2 size={15} />} Entfernen
          </button>
        </>
      }
    >
      {items.length === 1 ? (
        <p className="break small">{items[0].title}</p>
      ) : (
        <ul className="break small bulk-list">
          {items.map((q) => (
            <li key={q.id}>{q.title}</li>
          ))}
        </ul>
      )}
      <label className="checkbox">
        <input type="checkbox" checked={fromClient} onChange={(e) => setFromClient(e.target.checked)} /> Auch aus dem Downloadclient entfernen
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={blocklist} onChange={(e) => setBlocklist(e.target.checked)} /> Release auf die Blocklist setzen
      </label>
      <label className={`checkbox ${blocklist ? "" : "disabled"}`}>
        <input type="checkbox" disabled={!blocklist} checked={blocklist && searchAgain} onChange={(e) => setSearchAgain(e.target.checked)} /> Danach erneut suchen
      </label>
    </Modal>
  );
}

function HistoryTab() {
  const [page, setPage] = useState(1);
  const [event, setEvent] = useState("");
  const pageSize = 50;
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["history", "all", page, event],
    queryFn: () => api.history(page, pageSize, event),
    placeholderData: (prev) => prev,
  });
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();
  const sel = useRowSelection(data?.records.map((h) => h.id) ?? []);
  const remove = useApiMutation((ids: number[]) => api.bulkDeleteHistory(ids), {
    invalidate: [["history"]],
    success: (r) => `${r.deleted} Verlaufseinträge gelöscht`,
    onSuccess: () => sel.clear(),
  });
  const removeSelected = async () => {
    const n = sel.list.length;
    const ok = await confirm({
      title: `${n} Verlaufseinträge löschen?`,
      message: "Die ausgewählten Einträge werden endgültig aus dem Verlauf entfernt.",
      confirmLabel: "Löschen",
      danger: true,
    });
    if (ok) remove.mutate(sel.list);
  };
  const goPage = (p: number) => {
    setPage(p);
    sel.clear();
  };
  const markFailed = async (id: number, title: string) => {
    const ok = await confirm({ title: "Als fehlgeschlagen markieren?", message: <>„{title}“ wird auf die Blocklist gesetzt und es wird erneut gesucht.</>, confirmLabel: "Markieren", danger: true });
    if (!ok) return;
    try {
      await api.markFailed(id);
      toast.success("Als fehlgeschlagen markiert – neue Suche gestartet");
      qc.invalidateQueries({ queryKey: ["blocklist"] });
      qc.invalidateQueries({ queryKey: ["history"] });
    } catch (e) {
      toast.error("Aktion fehlgeschlagen", errorMessage(e));
    }
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  return (
    <>
      <div className="toolbar">
        <Select
          value={event}
          onValue={(v) => {
            setEvent(v);
            setPage(1);
            sel.clear();
          }}
          aria-label="Ereignis filtern"
          options={[{ value: "", label: "Alle Ereignisse" }, ...Object.entries(HISTORY_EVENT_LABELS).map(([k, l]) => ({ value: k, label: l }))]}
        />
        {data && <span className="muted">{data.total} Einträge</span>}
        {isFetching && <Spinner />}
        <span className="ml-auto" />
        <Pager page={page} pages={pages} onPage={goPage} />
      </div>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && (
        <HistoryTable
          records={data.records}
          showTitle
          selection={sel}
          actions={(h) =>
            h.event === "grabbed" || h.event === "imported" || h.event === "upgraded" ? (
              <button className="icon-btn danger" title="Als fehlgeschlagen markieren" aria-label="Als fehlgeschlagen markieren" onClick={() => markFailed(h.id, h.source_title)}>
                <XOctagon size={15} />
              </button>
            ) : null
          }
        />
      )}
      <BulkBar sel={sel}>
        <button className="btn btn-danger-outline" onClick={removeSelected} disabled={remove.isPending}>
          {remove.isPending ? <Spinner size={14} /> : <Trash2 size={15} />} Löschen
        </button>
      </BulkBar>
      <div className="row mt">
        <span className="ml-auto" />
        <Pager page={page} pages={pages} onPage={goPage} />
      </div>
    </>
  );
}

function BlocklistTab() {
  const { data, isLoading, error } = useQuery({ queryKey: ["blocklist"], queryFn: api.blocklist });
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteBlocklist(id), { invalidate: [["blocklist"]], success: "Aus der Blocklist entfernt" });
  const clear = useApiMutation(() => api.clearBlocklist(), { invalidate: [["blocklist"]], success: (r) => `${r.deleted} Einträge entfernt` });
  const sel = useRowSelection(data?.map((b) => b.id) ?? []);
  const delMany = useApiMutation((ids: number[]) => api.bulkDeleteBlocklist(ids), {
    invalidate: [["blocklist"]],
    success: (r) => `${r.deleted} Einträge aus der Blocklist entfernt`,
    onSuccess: () => sel.clear(),
  });
  const delSelected = async () => {
    const n = sel.list.length;
    const ok = await confirm({
      title: `${n} Einträge aus der Blocklist entfernen?`,
      message: "Diese Releases können danach wieder geladen werden.",
      confirmLabel: "Entfernen",
      danger: true,
    });
    if (ok) delMany.mutate(sel.list);
  };
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  return (
    <>
      <div className="toolbar">
        <span className="muted">{data?.length ?? 0} Einträge</span>
        <button
          className="btn btn-danger-outline ml-auto"
          disabled={!data?.length}
          onClick={async () => {
            if (await confirm({ title: "Blocklist leeren?", message: "Alle Einträge werden entfernt.", confirmLabel: "Leeren", danger: true })) clear.mutate(undefined);
          }}
        >
          <Trash2 size={15} /> Alle entfernen
        </button>
      </div>
      {!data?.length ? (
        <Empty title="Die Blocklist ist leer" />
      ) : (
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <SelectHead sel={sel} />
                <th>Release</th>
                <th>Medium</th>
                <th>Indexer</th>
                <th>Grund</th>
                <th>Datum</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {data.map((b) => (
                <tr key={b.id} className={sel.ids.has(b.id) ? "row-selected" : ""}>
                  <SelectCell sel={sel} id={b.id} />
                  <td className="break small">{b.source_title}</td>
                  <td>{b.movie_id ? <Link to={`/movies/${b.movie_id}`}>Film</Link> : b.series_id ? <Link to={`/series/${b.series_id}`}>Serie</Link> : "–"}</td>
                  <td className="small">
                    {b.indexer ?? "–"} {b.protocol && <span className="muted">({b.protocol})</span>}
                  </td>
                  <td className="small">{b.reason ?? "–"}</td>
                  <td className="nowrap small">{fmtDateTime(b.date)}</td>
                  <td className="actions">
                    <button className="icon-btn danger" title="Entfernen" aria-label="Entfernen" onClick={() => del.mutate(b.id)}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <BulkBar sel={sel}>
        <button className="btn btn-danger-outline" onClick={delSelected} disabled={delMany.isPending}>
          {delMany.isPending ? <Spinner size={14} /> : <Trash2 size={15} />} Entfernen
        </button>
      </BulkBar>
    </>
  );
}

function PendingTab() {
  const { data, isLoading, error } = useQuery({ queryKey: ["pending"], queryFn: api.pending, refetchInterval: 30_000 });
  const grab = useApiMutation((id: number) => api.grabPending(id), {
    invalidate: [["pending"], ["queue"]],
    success: (r) => (r.grabbed ? "Release wird geladen" : r.errors[0] ?? "Release ist nicht mehr gültig"),
  });
  const drop = useApiMutation((id: number) => api.deletePending(id), { invalidate: [["pending"]], success: "Verworfen" });
  const sel = useRowSelection(data?.map((p) => p.id) ?? []);
  const confirm = useConfirm();
  const dropMany = useApiMutation((ids: number[]) => api.bulkDeletePending(ids), {
    invalidate: [["pending"]],
    success: (r) => `${r.deleted} Releases verworfen`,
    onSuccess: () => sel.clear(),
  });
  const dropSelected = async () => {
    const n = sel.list.length;
    const ok = await confirm({
      title: `${n} Releases verwerfen?`,
      message: "Die ausgewählten zurückgestellten Releases werden nicht mehr geladen.",
      confirmLabel: "Verwerfen",
      danger: true,
    });
    if (ok) dropMany.mutate(sel.list);
  };
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.length)
    return (
      <Empty title="Nichts zurückgestellt">
        <p className="muted">Hier landen Releases, die wegen eines Delay-Profils noch warten.</p>
      </Empty>
    );
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <SelectHead sel={sel} />
              <th>Für</th>
              <th>Release</th>
              <th>Qualität</th>
              <th>Indexer</th>
              <th className="num">Größe</th>
              <th>Lädt ab</th>
              <th className="w-actions" />
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id} className={sel.ids.has(p.id) ? "row-selected" : ""}>
                <SelectCell sel={sel} id={p.id} />
                <td>
                  <Link to={p.movie_id ? `/movies/${p.movie_id}` : `/series/${p.series_id}`} className="strong">
                    {p.target}
                  </Link>
                </td>
                <td className="small break" title={p.reason ?? undefined}>
                  {p.protocol === "torrent" ? <Magnet size={13} /> : <Newspaper size={13} />} {p.title}
                </td>
                <td>
                  <Badge>{p.quality}</Badge> {p.format_score ? <Badge tone="muted">{p.format_score}</Badge> : null}
                </td>
                <td className="small">{p.indexer ?? "–"}</td>
                <td className="num">{fmtSize(p.size)}</td>
                <td className="small nowrap">{fmtDateTime(p.release_at)}</td>
                <td className="actions">
                  <button className="icon-btn" title="Jetzt laden" aria-label="Jetzt laden" onClick={() => grab.mutate(p.id)} disabled={grab.isPending}>
                    <Download size={15} />
                  </button>
                  <button className="icon-btn danger" title="Verwerfen" aria-label="Verwerfen" onClick={() => drop.mutate(p.id)}>
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <BulkBar sel={sel}>
        <button className="btn btn-danger-outline" onClick={dropSelected} disabled={dropMany.isPending}>
          {dropMany.isPending ? <Spinner size={14} /> : <Trash2 size={15} />} Verwerfen
        </button>
      </BulkBar>
    </>
  );
}
