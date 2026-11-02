import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, Link2 } from "lucide-react";
import { api, errorMessage } from "../../api";
import { Badge, Empty, ErrorBox, Spinner } from "../../components/ui";
import { Modal, useConfirm } from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { LookupCard } from "./AddMovie";
import type { LookupResult } from "../../types";

/** Assign a movie/series to a different metadata entry when the automatic match was wrong. */
export function RematchDialog({ kind, item, onClose }: { kind: "movie" | "series"; item: { id: number; title: string }; onClose: () => void }) {
  const [term, setTerm] = useState(item.title);
  const [q, setQ] = useState(item.title);
  const [busy, setBusy] = useState(false);
  const { data, isFetching, error } = useQuery({
    queryKey: ["lookup", kind, q],
    queryFn: () => (kind === "movie" ? api.lookupMovie(q) : api.lookupSeries(q)),
    enabled: q.trim().length > 0,
    staleTime: 300_000,
  });
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();
  const noun = kind === "movie" ? "Film" : "Serie";
  const prefix = kind === "movie" ? "tmdb:603, imdb:tt0133093" : "tvdb:81189, tmdb:1396, tvmaze:169";

  const pick = async (r: LookupResult) => {
    const ok = await confirm({
      title: `${noun} neu zuordnen`,
      confirmLabel: "Neu zuordnen",
      message: (
        <>
          <p>
            „{item.title}“ wird zu <strong>„{r.title}{r.year ? ` (${r.year})` : ""}“</strong>.
          </p>
          <p className="muted">
            {kind === "movie"
              ? "Titel, Beschreibung, Bilder und IDs werden ersetzt. Ordner, Datei und Einstellungen bleiben."
              : "Titel, Beschreibung, Bilder, IDs und die Episodenliste werden ersetzt. Dateien bleiben bei ihrer Staffel-/Episodennummer; Episoden, die es bei der neuen Serie nicht gibt, verlieren nur die Zuordnung, nicht die Datei."}
          </p>
        </>
      ),
    });
    if (!ok) return;
    setBusy(true);
    try {
      const res = kind === "movie" ? await api.rematchMovie(item.id, r.ids) : await api.rematchSeries(item.id, r.ids);
      toast.success(`${noun} neu zugeordnet`, res.title);
      qc.invalidateQueries({ queryKey: [kind === "movie" ? "movies" : "series"] });
      qc.invalidateQueries({ queryKey: [kind === "movie" ? "movie" : "series", item.id] });
      qc.invalidateQueries({ queryKey: ["episodes", item.id] });
      qc.invalidateQueries({ queryKey: ["lookup"] });
      onClose();
    } catch (e) {
      toast.error("Neu zuordnen fehlgeschlagen", errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`${noun} neu zuordnen: ${item.title}`} size="lg" onClose={onClose}>
      <p className="muted">
        Falls die automatische Erkennung danebenlag: richtigen Eintrag suchen und auswählen. Direkt per ID geht auch, z. B. {prefix} oder anilist:ID.
      </p>
      <form
        className="lookup-form"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(term.trim());
        }}
      >
        <div className="search-box search-box-lg">
          <Search size={18} />
          <input className="input" autoFocus value={term} onChange={(e) => setTerm(e.target.value)} aria-label={`${noun} suchen`} />
        </div>
        <button className="btn btn-primary" type="submit" disabled={!term.trim()}>
          Suchen
        </button>
      </form>
      <div className="rematch-results">
        {isFetching && <div className="loading-block"><Spinner size={22} label="Durchsuche Metadaten-Provider…" /></div>}
        {error ? <ErrorBox error={error} title="Suche fehlgeschlagen" /> : null}
        {!isFetching && data?.length === 0 && <Empty title={`Keine Ergebnisse für „${q}“`} />}
        {!isFetching &&
          data?.map((r, i) => {
            const current = r.existing_id === item.id;
            const other = r.existing_id != null && !current;
            return (
              <LookupCard
                key={`${JSON.stringify(r.ids)}-${i}`}
                r={{ ...r, existing_id: other ? r.existing_id : null }}
                kind={kind}
                action={
                  current ? (
                    <Badge tone="info">Aktuelle Zuordnung</Badge>
                  ) : other ? (
                    <Link to={`/${kind === "movie" ? "movies" : "series"}/${r.existing_id}`} className="btn" onClick={onClose}>Öffnen</Link>
                  ) : (
                    <button className="btn btn-primary" onClick={() => pick(r)} disabled={busy}>
                      {busy ? <Spinner size={14} /> : <Link2 size={16} />} Zuordnen
                    </button>
                  )
                }
              />
            );
          })}
      </div>
    </Modal>
  );
}
