import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Modal } from "../../components/Modal";
import { ErrorBox, Loading } from "../../components/ui";
import type { RenamePreview } from "../../types";

export function RenameDialog({ load, queryKey, onApply, onClose }: { load: () => Promise<RenamePreview[]>; queryKey: unknown[]; onApply: () => void; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({ queryKey, queryFn: load, staleTime: 0, gcTime: 0 });
  return (
    <Modal
      title="Umbenennen – Vorschau"
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {data?.length ? "Abbrechen" : "Schließen"}
          </button>
          {!!data?.length && (
            <button
              className="btn btn-primary"
              onClick={() => {
                onApply();
                onClose();
              }}
            >
              {data.length} Datei(en) umbenennen
            </button>
          )}
        </>
      }
    >
      {isLoading && <Loading />}
      {error ? <ErrorBox error={error} /> : null}
      {data && data.length === 0 && (
        <div className="health-ok">
          <CheckCircle2 size={18} /> Alle Dateien sind bereits korrekt benannt.
        </div>
      )}
      {data && data.length > 0 && (
        <ul className="rename-list">
          {data.map((r) => (
            <li key={r.file_id}>
              <div className="rename-old mono">{r.existing}</div>
              <ArrowRight size={14} className="muted" />
              <div className="rename-new mono">{r.new}</div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
