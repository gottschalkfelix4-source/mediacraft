import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RotateCcw, CheckCircle2, XCircle, Hand, Bot, Pencil, PlayCircle, PauseCircle } from "lucide-react";
import { api } from "../../api";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Select } from "../../components/ui";
import { useConfirm } from "../../components/Modal";
import { UsageMeter, windowLabel } from "../../components/Usage";
import { useApiMutation, useNow } from "../../hooks";
import { fmtDateTime, parseDate, relTime } from "../../format";
import { ForecastChart, UsageHistogram } from "./Charts";
import { IndexerDialog } from "./IndexerDialog";

const KIND_LABELS: Record<string, string> = { query: "Suche", rss: "RSS", grab: "Grab", caps: "Caps" };

export function IndexerUsagePage() {
  const id = Number(useParams().id);
  const [hours, setHours] = useState(48);
  const { data, isLoading, error } = useQuery({ queryKey: ["indexer-usage", id, hours], queryFn: () => api.indexerUsage(id, hours), refetchInterval: 60_000 });
  const now = useNow(30_000);
  const confirm = useConfirm();
  const [kind, setKind] = useState("");
  const [editing, setEditing] = useState(false);
  const reset = useApiMutation(() => api.resetIndexerUsage(id), {
    invalidate: [["indexer-usage", id], ["indexers"], ["indexers-usage"]],
    success: (r) => `${r.deleted} Ereignisse gelöscht`,
  });
  const unpause = useApiMutation(() => api.unpauseIndexer(id), { invalidate: [["indexer-usage", id], ["indexers"], ["indexers-usage"]], success: "Pause aufgehoben" });

  const events = useMemo(() => (data?.events ?? []).filter((e) => !kind || e.kind === kind), [data, kind]);
  const totals = useMemo(() => {
    const h = data?.histogram ?? [];
    return { query: h.reduce((a, b) => a + b.query, 0), grab: h.reduce((a, b) => a + b.grab, 0), failed: h.reduce((a, b) => a + b.failed, 0) };
  }, [data]);

  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const i = data.indexer;
  const paused = !!i.disabled_until && (parseDate(i.disabled_until)?.getTime() ?? 0) > now.getTime();

  return (
    <div className="page">
      <PageHeader
        title={
          <>
            <Link to="/indexers" className="icon-btn back-btn" title="Zurück zu den Indexern" aria-label="Zurück">
              <ArrowLeft size={18} />
            </Link>
            {i.name} <span className="muted">– Nutzung</span>
          </>
        }
        sub={`${i.protocol === "torrent" ? "Torznab" : "Newznab"} · ${windowLabel(i.limit_mode, i.limit_window_hours, i.limit_reset_hour)}${i.grab_reserve ? ` · ${i.grab_reserve} Grabs Reserve` : ""}`}
      >
        {paused && (
          <button className="btn" onClick={() => unpause.mutate(undefined)}>
            <PlayCircle size={15} /> Fortsetzen
          </button>
        )}
        <button className="btn" onClick={() => setEditing(true)}>
          <Pencil size={15} /> Bearbeiten
        </button>
        <button
          className="btn btn-danger-outline"
          onClick={async () => {
            if (
              await confirm({
                title: "Nutzungsdaten zurücksetzen?",
                message: "Alle gespeicherten Query-/Grab-Ereignisse dieses Indexers werden gelöscht. Die Zähler starten bei 0 – vom Indexer gemeldete Zähler gelten weiterhin.",
                confirmLabel: "Zurücksetzen",
                danger: true,
              })
            )
              reset.mutate(undefined);
          }}
        >
          <RotateCcw size={15} /> Zurücksetzen
        </button>
      </PageHeader>

      {paused && (
        <div className="alert alert-warning">
          <PauseCircle size={16} /> Pausiert bis {fmtDateTime(i.disabled_until)} ({relTime(i.disabled_until, now)}) {i.last_error ? `– ${i.last_error}` : ""}
        </div>
      )}

      {i.usage && (
        <div className="usage-pair usage-pair-lg mb">
          <Card>
            <UsageMeter st={i.usage.query} now={now} />
          </Card>
          <Card>
            <UsageMeter st={i.usage.grab} now={now} />
          </Card>
        </div>
      )}

      <Card
        title={`Anfragen pro Stunde`}
        actions={
          <>
            <span className="muted small">
              {totals.query} Queries · {totals.grab} Grabs · {totals.failed} Fehler
            </span>
            <Select
              value={hours}
              onValue={setHours}
              aria-label="Zeitraum"
              options={[
                { value: 24, label: "24 Stunden" },
                { value: 48, label: "48 Stunden" },
                { value: 72, label: "3 Tage" },
                { value: 168, label: "7 Tage" },
              ]}
            />
          </>
        }
      >
        <UsageHistogram data={data.histogram} />
      </Card>

      <Card title="Verfügbar in den nächsten 24 h">
        <div className="forecast-pair">
          <ForecastChart points={data.forecast.grab} limit={i.usage?.grab.limit ?? 0} reserve={i.grab_reserve} label="Verfügbare Grabs" tone="grab" />
          <ForecastChart points={data.forecast.query} limit={i.usage?.query.limit ?? 0} reserve={i.query_reserve} label="Verfügbare Queries" tone="query" />
        </div>
      </Card>

      <Card
        title="Letzte Ereignisse"
        actions={
          <Select
            value={kind}
            onValue={setKind}
            aria-label="Art filtern"
            options={[{ value: "", label: "Alle Arten" }, ...Object.entries(KIND_LABELS).map(([k, l]) => ({ value: k, label: l }))]}
          />
        }
      >
        {events.length === 0 ? (
          <Empty title="Keine Ereignisse" />
        ) : (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Art</th>
                  <th>Zeit</th>
                  <th>Erfolg</th>
                  <th>Auslöser</th>
                  <th className="num">Dauer</th>
                  <th className="num">Ergebnisse</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className={e.success ? "" : "row-err"}>
                    <td>
                      <Badge tone={e.kind === "grab" ? "success" : e.kind === "rss" ? "accent" : e.kind === "caps" ? "muted" : "info"}>{KIND_LABELS[e.kind] ?? e.kind}</Badge>
                    </td>
                    <td className="nowrap small" title={relTime(e.timestamp, now)}>
                      {fmtDateTime(e.timestamp)}
                    </td>
                    <td>{e.success ? <CheckCircle2 size={15} className="tone-text-success" /> : <XCircle size={15} className="tone-text-danger" />}</td>
                    <td className="small">
                      {e.manual ? (
                        <span title="Manuell">
                          <Hand size={13} /> manuell
                        </span>
                      ) : (
                        <span className="muted" title="Automatisch">
                          <Bot size={13} /> auto
                        </span>
                      )}
                    </td>
                    <td className="num small">{e.elapsed_ms ? `${e.elapsed_ms} ms` : "–"}</td>
                    <td className="num small">{e.kind === "grab" ? "–" : e.results}</td>
                    <td className="small break">{e.detail || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {editing && <IndexerDialog indexer={i} onClose={() => setEditing(false)} />}
    </div>
  );
}
