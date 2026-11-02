import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Info } from "lucide-react";
import { Badge, Empty } from "../../components/ui";
import { Modal } from "../../components/Modal";
import { fmtDateTime, HISTORY_EVENT_LABELS } from "../../format";
import type { HistoryRecord } from "../../types";

export const EVENT_TONE: Record<string, "success" | "info" | "accent" | "danger" | "muted" | "warning"> = {
  grabbed: "info",
  imported: "success",
  upgraded: "accent",
  failed: "danger",
  deleted: "warning",
  renamed: "muted",
  ignored: "muted",
};

export function HistoryTable({ records, showTitle, actions }: { records: HistoryRecord[]; showTitle?: boolean; actions?: (h: HistoryRecord) => ReactNode }) {
  const [detail, setDetail] = useState<HistoryRecord | null>(null);
  if (!records.length) return <Empty title="Kein Verlauf vorhanden" />;
  return (
    <>
      <div className="table-wrap">
        <table className="table table-compact">
          <thead>
            <tr>
              <th>Ereignis</th>
              {showTitle && <th>Titel</th>}
              <th>Release / Datei</th>
              <th>Qualität</th>
              <th>Indexer / Client</th>
              <th>Datum</th>
              <th className="w-actions" />
            </tr>
          </thead>
          <tbody>
            {records.map((h) => (
              <tr key={h.id}>
                <td>
                  <Badge tone={EVENT_TONE[h.event] ?? "default"}>{HISTORY_EVENT_LABELS[h.event] ?? h.event}</Badge>
                </td>
                {showTitle && (
                  <td>
                    {h.movie_id ? (
                      <Link to={`/movies/${h.movie_id}`}>{h.title ?? `Film #${h.movie_id}`}</Link>
                    ) : h.series_id ? (
                      <Link to={`/series/${h.series_id}`}>{h.title ?? `Serie #${h.series_id}`}</Link>
                    ) : (
                      "–"
                    )}
                  </td>
                )}
                <td className="break small">{h.source_title}</td>
                <td>{h.quality ? <Badge tone="info">{h.quality}</Badge> : "–"}</td>
                <td className="small">{[h.indexer, h.download_client].filter(Boolean).join(" · ") || "–"}</td>
                <td className="nowrap small">{fmtDateTime(h.date)}</td>
                <td className="actions">
                  <button className="icon-btn" title="Details" aria-label="Details" onClick={() => setDetail(h)}>
                    <Info size={15} />
                  </button>
                  {actions?.(h)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail && (
        <Modal title="Verlaufsdetails" onClose={() => setDetail(null)} size="lg">
          <dl className="kv">
            <div className="kv-row"><dt>Ereignis</dt><dd>{HISTORY_EVENT_LABELS[detail.event] ?? detail.event}</dd></div>
            <div className="kv-row"><dt>Datum</dt><dd>{fmtDateTime(detail.date)}</dd></div>
            <div className="kv-row"><dt>Release</dt><dd className="break">{detail.source_title}</dd></div>
            <div className="kv-row"><dt>Qualität</dt><dd>{detail.quality ?? "–"}</dd></div>
            <div className="kv-row"><dt>Indexer</dt><dd>{detail.indexer ?? "–"}</dd></div>
            <div className="kv-row"><dt>Downloadclient</dt><dd>{detail.download_client ?? "–"}</dd></div>
            <div className="kv-row"><dt>Download-ID</dt><dd className="mono break">{detail.download_id ?? "–"}</dd></div>
          </dl>
          {detail.data && Object.keys(detail.data).length > 0 && <pre className="code-block">{JSON.stringify(detail.data, null, 2)}</pre>}
        </Modal>
      )}
    </>
  );
}
