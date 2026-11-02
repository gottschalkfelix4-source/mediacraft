import { Fragment, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle, Clock, Download, AlertTriangle, ChevronDown, ChevronRight, ExternalLink, RefreshCw, Magnet, Newspaper } from "lucide-react";
import { api, errorMessage } from "../api";
import { fmtAge, fmtSize, langLabel } from "../format";
import type { Decision } from "../types";
import { Modal, useConfirm } from "./Modal";
import { useToast } from "./Toast";
import { Badge, Empty, ErrorBox, Spinner, Toggle } from "./ui";

type SortKey = "rank" | "title" | "indexer" | "age" | "size" | "seeders" | "quality" | "score";

export function InteractiveSearch({ title, queryKey, fetcher, onClose }: {
  title: string;
  queryKey: unknown[];
  fetcher: () => Promise<{ releases: Decision[]; errors: string[]; indexers: number }>;
  onClose: () => void;
}) {
  const { data, isFetching, error, refetch } = useQuery({
    queryKey: ["releases", ...queryKey],
    queryFn: fetcher,
    staleTime: 0,
    gcTime: 60_000,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const [showRejected, setShowRejected] = useState(true);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "rank", dir: 1 });
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [grabbing, setGrabbing] = useState<string | null>(null);
  const [grabbed, setGrabbed] = useState<Set<string>>(new Set());
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const rows = useMemo(() => {
    let list = (data?.releases ?? []).map((d, i) => ({ d, i }));
    if (!showRejected) list = list.filter(({ d }) => d.approved);
    if (filter) {
      const f = filter.toLowerCase();
      list = list.filter(({ d }) => d.release.title.toLowerCase().includes(f) || d.release.indexer.toLowerCase().includes(f));
    }
    const val = (d: Decision, i: number): number | string => {
      switch (sort.key) {
        case "title": return d.release.title.toLowerCase();
        case "indexer": return d.release.indexer.toLowerCase();
        case "age": return d.release.age_hours;
        case "size": return d.release.size;
        case "seeders": return d.release.seeders ?? -1;
        case "quality": return d.quality;
        case "score": return d.format_score;
        default: return i;
      }
    };
    return [...list].sort((a, b) => {
      const va = val(a.d, a.i);
      const vb = val(b.d, b.i);
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
    });
  }, [data, showRejected, filter, sort]);

  const key = (d: Decision) => `${d.release.indexer_id}|${d.release.guid}`;

  const grab = async (d: Decision) => {
    let force = false;
    if (!d.approved) {
      const ok = await confirm({
        title: "Abgelehntes Release laden?",
        message: (
          <>
            <p>
              <strong>{d.release.title}</strong>
            </p>
            <p>Dieses Release wurde abgelehnt:</p>
            <ul className="reject-list">
              {d.rejections.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <p>Trotzdem herunterladen?</p>
          </>
        ),
        confirmLabel: "Trotzdem laden",
        danger: true,
      });
      if (!ok) return;
      force = true;
    }
    const k = key(d);
    setGrabbing(k);
    try {
      await api.grabRelease(d.release.indexer_id, d.release.guid, force);
      toast.success("Release an Downloadclient gesendet", d.release.title);
      setGrabbed((s) => new Set(s).add(k));
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["indexers-usage"] });
    } catch (e) {
      toast.error("Grab fehlgeschlagen", errorMessage(e));
    } finally {
      setGrabbing(null);
    }
  };

  const th = (k: SortKey, label: string, cls?: string) => (
    <th className={`sortable ${cls ?? ""}`} onClick={() => setSort((s) => ({ key: k, dir: s.key === k ? ((-s.dir) as 1 | -1) : k === "title" || k === "indexer" || k === "rank" ? 1 : -1 }))}>
      {label}
      {sort.key === k && <span className="sort-ind">{sort.dir === 1 ? "▲" : "▼"}</span>}
    </th>
  );

  const approvedCount = data?.releases.filter((d) => d.approved).length ?? 0;

  return (
    <Modal title={title} size="xl" onClose={onClose} className="release-modal">
      <div className="toolbar">
        <input className="input" placeholder="Filtern…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Releases filtern" />
        <Toggle checked={showRejected} onChange={setShowRejected} label="Abgelehnte anzeigen" />
        <span className="muted">
          {data ? `${data.releases.length} Releases · ${approvedCount} akzeptiert · ${data.indexers} Indexer` : ""}
        </span>
        <button className="btn btn-sm ml-auto" onClick={() => refetch()} disabled={isFetching} title="Erneut suchen">
          <RefreshCw size={14} className={isFetching ? "spin" : ""} /> Neu suchen
        </button>
      </div>
      {data?.errors?.length ? (
        <div className="alert alert-warning">
          <AlertTriangle size={16} />
          <div>
            {data.errors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        </div>
      ) : null}
      {error ? <ErrorBox error={error} title="Suche fehlgeschlagen" /> : null}
      {isFetching && !data && (
        <div className="loading-block">
          <Spinner size={22} label="Durchsuche Indexer… (kann etwas dauern)" />
        </div>
      )}
      {data && !rows.length && <Empty title="Keine Releases gefunden" />}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="table table-compact releases">
            <thead>
              <tr>
                <th className="w-icon" />
                {th("title", "Release")}
                {th("indexer", "Indexer")}
                {th("age", "Alter", "num")}
                {th("size", "Größe", "num")}
                {th("seeders", "Peers", "num")}
                {th("quality", "Qualität")}
                <th>Sprache</th>
                {th("score", "Formate", "num")}
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map(({ d }) => {
                const k = key(d);
                const r = d.release;
                const isOpen = open.has(k);
                const status = d.approved ? "ok" : d.temporary ? "temp" : "rej";
                return (
                  <Fragment key={k}>
                    <tr className={`rel-${status}`}>
                      <td>
                        <button
                          className={`icon-btn rel-status rel-status-${status}`}
                          title={d.approved ? "Akzeptiert" : (d.temporary ? "Vorübergehend abgelehnt:\n" : "Abgelehnt:\n") + d.rejections.join("\n")}
                          aria-label="Details"
                          onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })}
                        >
                          {d.approved ? <CheckCircle2 size={17} /> : d.temporary ? <Clock size={17} /> : <XCircle size={17} />}
                        </button>
                      </td>
                      <td className="rel-title">
                        <button className="link-btn" onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })}>
                          {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {r.title}
                        </button>
                        {!d.approved && !isOpen && <div className={`rel-reason ${d.temporary ? "tone-text-warning" : "tone-text-danger"}`}>{d.rejections[0]}{d.rejections.length > 1 ? ` (+${d.rejections.length - 1})` : ""}</div>}
                      </td>
                      <td>
                        <span className="nowrap">
                          {r.protocol === "torrent" ? <Magnet size={12} className="muted" /> : <Newspaper size={12} className="muted" />} {r.indexer}
                        </span>
                      </td>
                      <td className="num nowrap">{fmtAge(r.age_hours)}</td>
                      <td className="num nowrap">{fmtSize(r.size)}</td>
                      <td className="num nowrap">{r.protocol === "torrent" ? `${r.seeders ?? "?"}/${r.leechers ?? "?"}` : r.grabs != null ? <span title="Grabs">{r.grabs}</span> : "–"}</td>
                      <td>
                        <Badge tone="info">{d.quality}</Badge>
                        {d.parsed.revision > 0 && <Badge tone="accent">Proper</Badge>}
                      </td>
                      <td>
                        <span className={d.language_match ? "" : "tone-text-warning"} title={d.language_match ? "Sprache passt" : "Sprache entspricht nicht dem Profil"}>
                          {d.parsed.languages.map(langLabel).join(", ") || "–"}
                        </span>
                      </td>
                      <td className="num">
                        {d.formats.length > 0 && (
                          <span className="cf-list" title={d.formats.join(", ")}>
                            {d.formats.slice(0, 3).map((f) => (
                              <span className="cf" key={f}>{f}</span>
                            ))}
                            {d.formats.length > 3 && <span className="cf">+{d.formats.length - 3}</span>}
                          </span>
                        )}
                        <span className={`score ${d.format_score > 0 ? "pos" : d.format_score < 0 ? "neg" : ""}`}>{d.format_score > 0 ? `+${d.format_score}` : d.format_score}</span>
                      </td>
                      <td className="actions">
                        {r.info_url && (
                          <a className="icon-btn" href={r.info_url} target="_blank" rel="noreferrer noopener" title="Details beim Indexer">
                            <ExternalLink size={15} />
                          </a>
                        )}
                        <button
                          className={`icon-btn grab-btn ${d.approved ? "approved" : "rejected"} ${grabbed.has(k) ? "done" : ""}`}
                          title={grabbed.has(k) ? "Bereits gesendet" : d.approved ? "Herunterladen" : "Trotzdem herunterladen (abgelehnt)"}
                          aria-label="Herunterladen"
                          disabled={grabbing === k}
                          onClick={() => grab(d)}
                        >
                          {grabbing === k ? <Spinner size={15} /> : grabbed.has(k) ? <CheckCircle2 size={16} /> : <Download size={16} />}
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="rel-details">
                        <td />
                        <td colSpan={9}>
                          {d.rejections.length > 0 && (
                            <div className="mb-sm">
                              <strong>{d.temporary ? "Vorübergehend abgelehnt (z. B. Limit/Warteschlange):" : "Ablehnungsgründe:"}</strong>
                              <ul className="reject-list">
                                {d.rejections.map((x, i) => (
                                  <li key={i}>{x}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          <div className="rel-meta">
                            <span>Erkannt: <strong>{d.parsed.title || "?"}</strong>{d.parsed.year ? ` (${d.parsed.year})` : ""}</span>
                            {d.parsed.seasons.length > 0 && <span>Staffel {d.parsed.seasons.join(", ")}{d.parsed.episodes.length ? ` · Episode ${d.parsed.episodes.join(", ")}` : d.parsed.full_season ? " · komplett" : ""}</span>}
                            {d.parsed.absolute_episodes.length > 0 && <span>Absolut {d.parsed.absolute_episodes.join(", ")}</span>}
                            {d.parsed.release_group && <span>Gruppe {d.parsed.release_group}</span>}
                            {d.parsed.codec && <span>Codec {d.parsed.codec}</span>}
                            {d.parsed.hdr.length > 0 && <span>HDR {d.parsed.hdr.join(", ")}</span>}
                            {d.parsed.audio.length > 0 && <span>Audio {d.parsed.audio.join(", ")}{d.parsed.audio_channels ? ` ${d.parsed.audio_channels}` : ""}</span>}
                            {d.parsed.edition && <span>Edition {d.parsed.edition}</span>}
                            {d.formats.length > 0 && <span>Custom Formats: {d.formats.join(", ")} (Score {d.format_score})</span>}
                            {r.flags.length > 0 && <span>Flags: {r.flags.join(", ")}</span>}
                            <span>Protokoll {r.protocol === "torrent" ? "Torrent" : "Usenet"}</span>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
