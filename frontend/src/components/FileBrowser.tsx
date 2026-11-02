import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, Folder, File, HardDrive } from "lucide-react";
import { api } from "../api";
import { fmtSize } from "../format";
import { Modal } from "./Modal";
import { ErrorBox, Spinner } from "./ui";

const norm = (p: string) => p.replace(/[\\/]+$/, "").toLowerCase();

/** Server-side filesystem browser (GET /filesystem). */
export function FileBrowser({ title = "Ordner wählen", initial = "", includeFiles = false, onSelect, onClose }: {
  title?: string;
  initial?: string;
  includeFiles?: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}) {
  const [path, setPath] = useState(initial);
  const [typed, setTyped] = useState(initial);
  const { data, isLoading, error } = useQuery({
    queryKey: ["fs", path, includeFiles],
    queryFn: () => api.filesystem(path, includeFiles),
  });

  const go = (p: string) => {
    setPath(p);
    setTyped(p);
  };

  return (
    <Modal
      title={title}
      size="lg"
      onClose={onClose}
      footer={
        <>
          {data?.free_space != null && <span className="muted mr-auto">Frei: {fmtSize(data.free_space)}</span>}
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary" disabled={!typed} onClick={() => onSelect(typed)}>
            Auswählen
          </button>
        </>
      }
    >
      <form
        className="row gap-sm mb"
        onSubmit={(e) => {
          e.preventDefault();
          go(typed);
        }}
      >
        <input className="input grow mono" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="/pfad/zum/ordner" aria-label="Pfad" />
        <button className="btn" type="submit">
          Öffnen
        </button>
      </form>
      {error ? <ErrorBox error={error} /> : null}
      {isLoading && <Spinner label="Lade Ordner…" />}
      {data && (
        <ul className="fs-list">
          {data.parent && norm(data.parent) !== norm(data.path) && (
            <li>
              <button className="fs-item" onClick={() => go(data.parent ?? "")}>
                <ArrowUp size={16} /> ..
              </button>
            </li>
          )}
          {data.path && (!data.parent || norm(data.parent) === norm(data.path)) && (
            <li>
              <button className="fs-item" onClick={() => go("")}>
                <HardDrive size={16} /> Laufwerke / Wurzel
              </button>
            </li>
          )}
          {data.dirs.map((d) => (
            <li key={d.path}>
              <button className="fs-item" onClick={() => go(d.path)} onDoubleClick={() => onSelect(d.path)}>
                <Folder size={16} className="accent" /> {d.name}
              </button>
            </li>
          ))}
          {data.files.map((f) => (
            <li key={f.path}>
              <button className="fs-item" onClick={() => setTyped(f.path)} onDoubleClick={() => onSelect(f.path)}>
                <File size={16} /> {f.name} <span className="muted ml-auto">{fmtSize(f.size)}</span>
              </button>
            </li>
          ))}
          {!data.dirs.length && !data.files.length && <li className="muted p-sm">Keine Unterordner</li>}
        </ul>
      )}
    </Modal>
  );
}
