import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, RotateCcw, XOctagon, AlertTriangle, Download, Magnet, Newspaper, RefreshCw } from "lucide-react";
import { api, errorMessage } from "../api";
import { Badge, Empty, ErrorBox, Loading, PageHeader, Pager, Progress, Select, Spinner, Tabs } from "../components/ui";
import { Modal, useConfirm } from "../components/Modal";
import { useToast } from "../components/Toast";
import { useApiMutation, useCommand } from "../hooks";
import { useEventListener } from "../events";
import { fmtDateTime, fmtDuration, fmtSize, HISTORY_EVENT_LABELS, langLabel, QUEUE_STATUS_LABELS } from "../format";
import { HistoryTable } from "./library/HistoryTable";
import type { QueueItem } from "../types";

type TabKey = "queue" | "history" | "blocklist";

export function ActivityPage() {
  const params = useParams();
  const tab = (["queue", "history", "blocklist"].includes(params.tab ?? "") ? params.tab : "queue") as TabKey;
  const nav = useNavigate();
  const command = useCommand();
  const queue = useQuery({ queryKey: ["queue"], queryFn: api.queue, refetchInterval: 5000 });
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
          { key: "history", label: "Verlauf" },
          { key: "blocklist", label: "Blocklist" },
        ]}
        active={tab}
        onChange={(k) => nav(`/activity/${k}`)}
      />
      {tab === "queue" && <QueueTab items={queue.data} loading={queue.isLoading} error={queue.error} />}
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

function QueueTab({ items, loading, error }: { items?: QueueItem[]; loading: boolean; error: unknown }) {
  const [removing, setRemoving] = useState<QueueItem | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const retry = async (q: QueueItem) => {
    try {
      const r = await api.retryQueueImport(q.id);
      if (r.ok) toast.success("Import erfolgreich", q.title);
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
                <tr key={q.id} className={problem ? "row-warn" : ""}>
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
                    <button className="icon-btn danger" title="Entfernen" aria-label="Entfernen" onClick={() => setRemoving(q)}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {removing && <RemoveQueueDialog q={removing} onClose={() => setRemoving(null)} />}
    </>
  );
}

function RemoveQueueDialog({ q, onClose }: { q: QueueItem; onClose: () => void }) {
  const [fromClient, setFromClient] = useState(true);
  const [blocklist, setBlocklist] = useState(false);
  const [searchAgain, setSearchAgain] = useState(false);
  const rm = useApiMutation(() => api.removeQueue(q.id, { remove_from_client: fromClient, blocklist, search_again: blocklist && searchAgain }), {
    invalidate: [["queue"], ["blocklist"]],
    success: "Aus der Warteschlange entfernt",
    onSuccess: onClose,
  });
  return (
    <Modal
      title="Aus Warteschlange entfernen"
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
      <p className="break small">{q.title}</p>
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
          }}
          aria-label="Ereignis filtern"
          options={[{ value: "", label: "Alle Ereignisse" }, ...Object.entries(HISTORY_EVENT_LABELS).map(([k, l]) => ({ value: k, label: l }))]}
        />
        {data && <span className="muted">{data.total} Einträge</span>}
        {isFetching && <Spinner />}
        <span className="ml-auto" />
        <Pager page={page} pages={pages} onPage={setPage} />
      </div>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && (
        <HistoryTable
          records={data.records}
          showTitle
          actions={(h) =>
            h.event === "grabbed" || h.event === "imported" || h.event === "upgraded" ? (
              <button className="icon-btn danger" title="Als fehlgeschlagen markieren" aria-label="Als fehlgeschlagen markieren" onClick={() => markFailed(h.id, h.source_title)}>
                <XOctagon size={15} />
              </button>
            ) : null
          }
        />
      )}
      <div className="row mt">
        <span className="ml-auto" />
        <Pager page={page} pages={pages} onPage={setPage} />
      </div>
    </>
  );
}

function BlocklistTab() {
  const { data, isLoading, error } = useQuery({ queryKey: ["blocklist"], queryFn: api.blocklist });
  const confirm = useConfirm();
  const del = useApiMutation((id: number) => api.deleteBlocklist(id), { invalidate: [["blocklist"]], success: "Aus der Blocklist entfernt" });
  const clear = useApiMutation(() => api.clearBlocklist(), { invalidate: [["blocklist"]], success: (r) => `${r.deleted} Einträge entfernt` });
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
                <tr key={b.id}>
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
    </>
  );
}
