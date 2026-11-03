import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Folder, FileVideo, RotateCcw, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Card, Empty, ErrorBox, Loading } from "../../components/ui";
import { useConfirm } from "../../components/Modal";
import { useApiMutation } from "../../hooks";
import { fmtDateTime, fmtSize } from "../../format";

export function RecycleBinPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["recyclebin"], queryFn: api.recycleBin });
  const confirm = useConfirm();
  const restore = useApiMutation((p: string) => api.recycleRestore(p), {
    invalidate: [["recyclebin"], ["movies"], ["series"]],
    success: (r) => `Wiederhergestellt: ${r.restored}`,
  });
  const remove = useApiMutation((p: string) => api.recycleDelete(p), { invalidate: [["recyclebin"]], success: "Endgültig gelöscht" });
  const empty = useApiMutation(() => api.recycleEmpty(), { invalidate: [["recyclebin"]], success: (r) => `${r.removed} Datei(en) gelöscht` });

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.folder)
    return (
      <Card title="Papierkorb">
        <Empty title="Kein Papierkorb eingerichtet">
          <p className="muted">
            Ersetzte und gelöschte Dateien werden derzeit sofort gelöscht. Unter <Link to="/settings/media">Einstellungen → Medienverwaltung</Link> einen
            Papierkorb-Ordner eintragen.
          </p>
        </Empty>
      </Card>
    );

  const total = data.entries.reduce((n, e) => n + e.size, 0);
  return (
    <Card
      title="Papierkorb"
      actions={
        <button
          className="btn btn-sm btn-danger-outline"
          disabled={!data.entries.length || empty.isPending}
          onClick={async () => {
            if (await confirm({ title: "Papierkorb leeren?", message: `${data.entries.length} Einträge (${fmtSize(total)}) werden endgültig gelöscht.`, confirmLabel: "Leeren", danger: true }))
              empty.mutate();
          }}
        >
          <Trash2 size={14} /> Leeren
        </button>
      }
    >
      <p className="muted small">
        {data.folder} · {data.days ? `wird nach ${data.days} Tagen automatisch geleert` : "wird nicht automatisch geleert"} · {fmtSize(total)}
      </p>
      {data.entries.length === 0 ? (
        <Empty title="Papierkorb ist leer" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Eintrag</th>
                <th>Ursprünglicher Ort</th>
                <th>Gelöscht</th>
                <th className="num">Größe</th>
                <th className="w-actions" />
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.path}>
                  <td className="small break">
                    {e.folder ? <Folder size={13} /> : <FileVideo size={13} />} {e.path}
                  </td>
                  <td className="mono small break">{e.original ?? <span className="muted">unbekannt</span>}</td>
                  <td className="small nowrap">{fmtDateTime(e.deleted)}</td>
                  <td className="num">{fmtSize(e.size)}</td>
                  <td className="actions">
                    <button className="icon-btn" title="Wiederherstellen" aria-label="Wiederherstellen" disabled={!e.original || restore.isPending} onClick={() => restore.mutate(e.path)}>
                      <RotateCcw size={15} />
                    </button>
                    <button
                      className="icon-btn danger"
                      title="Endgültig löschen"
                      aria-label="Endgültig löschen"
                      onClick={async () => {
                        if (await confirm({ title: "Endgültig löschen?", message: e.path, confirmLabel: "Löschen", danger: true })) remove.mutate(e.path);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
