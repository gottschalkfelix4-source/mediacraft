import { useQuery } from "@tanstack/react-query";
import { Play, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Card, ErrorBox, Loading, Empty } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useNow } from "../../hooks";
import { userCommandIds } from "../../events";
import { commandLabel, fmtDateTime, fmtDuration, parseDate, relTime } from "../../format";

export function TasksPage() {
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.tasks, refetchInterval: 15_000 });
  const commands = useQuery({ queryKey: ["commands"], queryFn: api.commands, refetchInterval: 5_000 });
  const now = useNow(15_000);
  const toast = useToast();

  const run = async (name: string, label: string) => {
    try {
      const c = await api.runTask(name);
      userCommandIds.add(c.id);
      toast.info(`${label} gestartet`);
      tasks.refetch();
      commands.refetch();
    } catch (e) {
      toast.error(`${label} fehlgeschlagen`, errorMessage(e));
    }
  };

  return (
    <div className="settings-page">
      <Card title="Geplante Aufgaben">
        {tasks.isLoading && <Loading />}
        {tasks.error ? <ErrorBox error={tasks.error} /> : null}
        {tasks.data && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Aufgabe</th>
                  <th>Intervall</th>
                  <th>Zuletzt</th>
                  <th>Dauer</th>
                  <th>Nächste</th>
                  <th>Status</th>
                  <th className="w-actions" />
                </tr>
              </thead>
              <tbody>
                {tasks.data.map((t) => (
                  <tr key={t.name}>
                    <td className="strong">{t.label}</td>
                    <td>{t.enabled ? fmtDuration(t.interval_seconds) : <Badge tone="muted">deaktiviert</Badge>}</td>
                    <td className="small" title={fmtDateTime(t.last_run)}>
                      {t.last_run ? relTime(t.last_run, now) : "nie"}
                    </td>
                    <td className="small">{t.last_duration_ms ? fmtDuration(t.last_duration_ms / 1000) : "–"}</td>
                    <td className="small" title={fmtDateTime(t.next_run)}>
                      {t.next_run ? ((parseDate(t.next_run)?.getTime() ?? 0) < now.getTime() ? "fällig" : relTime(t.next_run, now)) : "–"}
                    </td>
                    <td>
                      {t.running ? (
                        <Badge tone="accent">
                          <Loader2 size={12} className="spin" /> läuft
                        </Badge>
                      ) : t.last_error ? (
                        <Badge tone="danger" title={t.last_error}>
                          Fehler
                        </Badge>
                      ) : t.last_run ? (
                        <Badge tone="success">OK</Badge>
                      ) : (
                        <span className="muted">–</span>
                      )}
                    </td>
                    <td className="actions">
                      <button className="icon-btn" title="Jetzt ausführen" aria-label={`${t.label} jetzt ausführen`} onClick={() => run(t.name, t.label)} disabled={t.running}>
                        <Play size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Befehle">
        {commands.isLoading && <Loading />}
        {commands.data?.length === 0 && <Empty title="Noch keine Befehle ausgeführt" />}
        {commands.data && commands.data.length > 0 && (
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Befehl</th>
                  <th>Parameter</th>
                  <th>Eingereiht</th>
                  <th>Dauer</th>
                  <th>Ergebnis / Fehler</th>
                </tr>
              </thead>
              <tbody>
                {commands.data.map((c) => {
                  const st = parseDate(c.started);
                  const en = parseDate(c.ended);
                  return (
                    <tr key={c.id} className={c.status === "failed" ? "row-err" : ""}>
                      <td>
                        {c.status === "completed" ? (
                          <CheckCircle2 size={15} className="tone-text-success" />
                        ) : c.status === "failed" ? (
                          <XCircle size={15} className="tone-text-danger" />
                        ) : c.status === "running" ? (
                          <Loader2 size={15} className="spin accent" />
                        ) : (
                          <Clock size={15} className="muted" />
                        )}
                      </td>
                      <td>{commandLabel(c.name)}</td>
                      <td className="mono small">{Object.keys(c.params ?? {}).length ? JSON.stringify(c.params) : ""}</td>
                      <td className="small nowrap">{fmtDateTime(c.queued)}</td>
                      <td className="small">{st && en ? fmtDuration((en.getTime() - st.getTime()) / 1000) : st ? "läuft…" : "–"}</td>
                      <td className="small break">{c.error ?? (c.result != null ? JSON.stringify(c.result).slice(0, 200) : "")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
