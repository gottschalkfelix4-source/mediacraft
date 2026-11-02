import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Download } from "lucide-react";
import { api } from "../../api";
import { ErrorBox, Loading, Select, Toggle, Empty } from "../../components/ui";
import { fmtDateTime } from "../../format";

const LEVELS = [
  { value: "", label: "Alle Level" },
  { value: "DEBUG", label: "Debug+" },
  { value: "INFO", label: "Info+" },
  { value: "WARNING", label: "Warnung+" },
  { value: "ERROR", label: "Fehler" },
];

export function LogsPage() {
  const [level, setLevel] = useState("");
  const [auto, setAuto] = useState(true);
  const [filter, setFilter] = useState("");
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["logs", level],
    queryFn: () => api.logs(level, 1000),
    refetchInterval: auto ? 5000 : false,
  });
  const rows = useMemo(() => {
    const f = filter.toLowerCase();
    return (data ?? []).filter((r) => !f || r.message.toLowerCase().includes(f) || r.logger.toLowerCase().includes(f));
  }, [data, filter]);

  const download = () => {
    const text = (data ?? [])
      .slice()
      .reverse()
      .map((r) => `${r.time} ${r.level.padEnd(8)} ${r.logger}: ${r.message}`)
      .join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "mediacraft-log.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="settings-page">
      <div className="toolbar">
        <Select value={level} onValue={setLevel} options={LEVELS} aria-label="Level" />
        <input className="input" placeholder="Filtern…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Logs filtern" />
        <Toggle checked={auto} onChange={setAuto} label="Automatisch aktualisieren" />
        <button className="btn btn-sm" onClick={() => refetch()} title="Aktualisieren">
          <RefreshCw size={14} className={isFetching ? "spin" : ""} /> Aktualisieren
        </button>
        <button className="btn btn-sm ml-auto" onClick={download} title="Als Textdatei speichern">
          <Download size={14} /> Speichern
        </button>
      </div>
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && rows.length === 0 && <Empty title="Keine Log-Einträge" />}
      {rows.length > 0 && (
        <div className="log-view">
          {rows.map((r) => (
            <div key={r.id} className={`log-row log-${r.level.toLowerCase()}`}>
              <span className="log-time">{fmtDateTime(r.time)}:{String(new Date(r.time).getSeconds()).padStart(2, "0")}</span>
              <span className="log-level">{r.level}</span>
              <span className="log-logger">{r.logger}</span>
              <span className="log-msg">{r.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
