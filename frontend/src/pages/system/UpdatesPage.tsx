import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, CheckCircle2, ExternalLink, GitCommit, RefreshCw } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Card, Empty, ErrorBox, KV, Loading } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { fmtDateTime } from "../../format";

export function UpdatesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["updates"], queryFn: () => api.updates(false), staleTime: 10 * 60_000 });
  const [checking, setChecking] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();

  const recheck = async () => {
    setChecking(true);
    try {
      qc.setQueryData(["updates"], await api.updates(true));
    } catch (e) {
      toast.error("Prüfung fehlgeschlagen", errorMessage(e));
    } finally {
      setChecking(false);
    }
  };

  if (isLoading) return <Loading label="Prüfe auf Updates…" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const c = data.current;

  return (
    <div className="settings-page">
      <Card
        title="Version"
        actions={
          <button className="btn btn-sm" onClick={recheck} disabled={checking}>
            <RefreshCw size={14} className={checking ? "spin" : ""} /> Jetzt prüfen
          </button>
        }
      >
        <KV
          items={[
            ["Version", `${c.version}${c.build ? ` (Build ${c.build})` : ""}`],
            ["Commit", c.commit ? <a href={`${c.repo}/commit/${c.commit}`} target="_blank" rel="noreferrer" className="mono">{c.commit}</a> : "unbekannt (Entwicklungsversion)"],
            ["Gebaut", c.build_date ? fmtDateTime(c.build_date) : "–"],
            ["Zuletzt geprüft", fmtDateTime(data.checked)],
          ]}
        />
        {data.error && <p className="tone-text-warning mt-sm">{data.error}</p>}
        {data.update_available === true && (
          <div className="alert mt">
            <ArrowUpCircle size={16} /> <strong>Neue Version verfügbar</strong> – {data.changes.length} Änderung(en). Den Container mit dem Image{" "}
            <code>ghcr.io/…/mediacraft:latest</code> neu ziehen und starten (Unraid: „Update“ beim Container).
          </div>
        )}
        {data.update_available === false && (
          <div className="health-ok mt">
            <CheckCircle2 size={18} /> MediaCraft ist aktuell
          </div>
        )}
      </Card>

      <Card
        title={data.update_available ? "Neu seit deiner Version" : "Letzte Änderungen"}
        actions={
          <a className="btn btn-sm" href={`${c.repo}/commits/main`} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> GitHub
          </a>
        }
      >
        {data.changes.length === 0 ? (
          <Empty title={data.update_available === false ? "Keine neuen Änderungen" : "Keine Daten"} />
        ) : (
          <ul className="changelog">
            {data.changes.map((ch) => (
              <li key={ch.sha}>
                <div className="row gap-sm">
                  <GitCommit size={14} className="muted" />
                  <strong>{ch.title}</strong>
                </div>
                <div className="muted small">
                  {fmtDateTime(ch.date)} ·{" "}
                  <a href={ch.url ?? undefined} target="_blank" rel="noreferrer" className="mono">
                    {ch.sha}
                  </a>
                </div>
                {ch.body && <pre className="changelog-body">{ch.body.replace(/\n*Co-Authored-By:.*$/s, "")}</pre>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
