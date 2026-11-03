import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, CheckCircle2, AlertTriangle, Info, HardDrive } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Card, ErrorBox, KV, Loading, Progress } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useNow } from "../../hooks";
import { fmtDateTime, fmtDuration, fmtSize, parseDate, relTime } from "../../format";
import { useState } from "react";

export function StatusPage() {
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const disk = useQuery({ queryKey: ["diskspace"], queryFn: api.diskspace });
  const now = useNow(30_000);
  const qc = useQueryClient();
  const toast = useToast();
  const [checking, setChecking] = useState(false);

  const refresh = async () => {
    setChecking(true);
    try {
      const h = await api.refreshHealth();
      qc.setQueryData(["health"], h);
      toast.success("Health-Check abgeschlossen", `${h.issues.length} Hinweis(e)`);
    } catch (e) {
      toast.error("Health-Check fehlgeschlagen", errorMessage(e));
    } finally {
      setChecking(false);
    }
  };

  const s = status.data;
  const started = parseDate(s?.started);
  return (
    <div className="settings-page">
      <Card
        title="Health"
        actions={
          <button className="btn btn-sm" onClick={refresh} disabled={checking}>
            <RefreshCw size={14} className={checking ? "spin" : ""} /> Jetzt prüfen
          </button>
        }
      >
        {health.isLoading && <Loading />}
        {health.error ? <ErrorBox error={health.error} /> : null}
        {health.data && health.data.issues.length === 0 && (
          <div className="health-ok">
            <CheckCircle2 size={18} /> Alles in Ordnung
          </div>
        )}
        {health.data && health.data.issues.length > 0 && (
          <ul className="issue-list">
            {health.data.issues.map((i, n) => (
              <li key={n} className={`issue issue-${i.level}`}>
                {i.level === "info" ? <Info size={16} /> : <AlertTriangle size={16} />}
                <span>{i.message}</span>
                <Badge tone="muted">{i.source}</Badge>
              </li>
            ))}
          </ul>
        )}
        {health.data?.checked && <div className="muted small mt-sm">Zuletzt geprüft {relTime(health.data.checked, now)}</div>}
      </Card>

      <Card title="Info">
        {status.isLoading && <Loading />}
        {status.error ? <ErrorBox error={status.error} /> : null}
        {s && (
          <KV
            items={[
              ["Version", `${s.app} ${s.version}${s.build ? ` · Build ${s.build}` : ""}${s.commit ? ` · ${s.commit}` : ""}`],
              ["Gestartet", started ? `${fmtDateTime(started)} (Laufzeit ${fmtDuration((now.getTime() - started.getTime()) / 1000)})` : "–"],
              ["Python", s.python],
              ["Betriebssystem", s.os],
              ["Docker", s.docker ? "ja" : "nein"],
              ["Konfigurationsordner", <span className="mono">{s.config_dir}</span>],
              ["Datenbank", <span className="mono">{s.db}</span>],
              ["URL-Basis", s.url_base || "–"],
              ["Bibliothek", `${s.movies} Filme · ${s.series} Serien`],
              ["Mediainfo", s.tools?.mediainfo ?? <span className="tone-text-warning">nicht installiert</span>],
              ["Entpacken", s.tools?.unpack.length ? s.tools.unpack.join(", ") : "nur ZIP"],
            ]}
          />
        )}
      </Card>

      <Card title="Speicherplatz">
        {disk.isLoading && <Loading />}
        {disk.data?.length === 0 && <div className="muted">Keine Root-Folder konfiguriert.</div>}
        <div className="disk-list">
          {disk.data?.map((d) => {
            const used = d.total - d.free;
            const pct = d.total ? (100 * used) / d.total : 0;
            return (
              <div key={d.path} className="disk">
                <div className="row gap-sm">
                  <HardDrive size={16} className="muted" />
                  <span className="mono grow">{d.path}</span>
                  <span className="small">
                    {fmtSize(d.free)} frei von {fmtSize(d.total)}
                  </span>
                </div>
                <Progress value={pct} tone={pct > 95 ? "danger" : pct > 85 ? "warning" : "accent"} />
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
