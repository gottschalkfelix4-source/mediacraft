import { useState } from "react";
import { Trash2 } from "lucide-react";
import { errorMessage } from "../../api";
import { Modal } from "../../components/Modal";
import { Spinner } from "../../components/ui";
import { useToast } from "../../components/Toast";

export function DeleteDialog({ title, path, onConfirm, onClose }: { title: string; path: string; onConfirm: (deleteFiles: boolean) => Promise<void>; onClose: () => void }) {
  const [files, setFiles] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  return (
    <Modal
      title={title}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button
            className="btn btn-danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm(files);
              } catch (e) {
                toast.error("Löschen fehlgeschlagen", errorMessage(e));
                setBusy(false);
              }
            }}
          >
            {busy ? <Spinner size={14} /> : <Trash2 size={15} />} Löschen
          </button>
        </>
      }
    >
      <p>Der Eintrag wird aus der Bibliothek entfernt.</p>
      <p className="mono small break">{path}</p>
      <label className="checkbox mt">
        <input type="checkbox" checked={files} onChange={(e) => setFiles(e.target.checked)} /> <strong>Dateien löschen</strong> – den kompletten Ordner von der Festplatte entfernen
      </label>
      {files && <div className="alert alert-error mt-sm">Achtung: Der Ordner und alle Dateien darin werden unwiderruflich gelöscht.</div>}
    </Modal>
  );
}
