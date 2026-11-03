import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Archive, Download, RotateCcw, Trash2, Upload, Power } from "lucide-react";
import { api, errorMessage, waitForServer } from "../../api";
import { Badge, Card, Empty, ErrorBox, Field, Loading, NumberInput, Spinner } from "../../components/ui";
import { useConfirm } from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { fmtDateTime, fmtSize } from "../../format";
import { SaveBar, useSection } from "../settings/common";
import type { BackupInfo, BackupSettings } from "../../types";

const KIND_LABELS: Record<BackupInfo["kind"], string> = {
  manual: "manuell",
  scheduled: "geplant",
  migration: "vor Update",
  restore: "vor Wiederherstellung",
};

export function BackupPage() {
  const list = useQuery({ queryKey: ["backups"], queryFn: api.backups });
  const section = useSection("backup");
  const confirm = useConfirm();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const afterRestart = async (what: string) => {
    setBusy("restart");
    toast.info(`${what} – MediaCraft startet neu…`);
    const back = await waitForServer();
    if (back) window.location.reload();
    else {
      setBusy(null);
      toast.error("MediaCraft antwortet nicht", "Container prüfen und ggf. von Hand neu starten");
    }
  };

  const create = async () => {
    setBusy("create");
    try {
      const b = await api.createBackup();
      toast.success("Backup erstellt", b.name);
      list.refetch();
    } catch (e) {
      toast.error("Backup fehlgeschlagen", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const restore = async (b: BackupInfo) => {
    const ok = await confirm({
      title: "Backup wiederherstellen?",
      message: (
        <>
          Datenbank und Einstellungen werden durch <b>{b.name}</b> ({fmtDateTime(b.created)}) ersetzt. Der aktuelle Stand wird vorher
          automatisch gesichert. MediaCraft startet dafür neu.
        </>
      ),
      confirmLabel: "Wiederherstellen",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.restoreBackup(b.name);
      await afterRestart("Wiederherstellung vorgemerkt");
    } catch (e) {
      toast.error("Wiederherstellung fehlgeschlagen", errorMessage(e));
    }
  };

  const upload = async (file: File) => {
    const ok = await confirm({
      title: "Backup-Datei wiederherstellen?",
      message: (
        <>
          Datenbank und Einstellungen werden durch <b>{file.name}</b> ersetzt. Der aktuelle Stand wird vorher automatisch gesichert. MediaCraft
          startet dafür neu.
        </>
      ),
      confirmLabel: "Wiederherstellen",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.restoreUpload(file);
      await afterRestart("Wiederherstellung vorgemerkt");
    } catch (e) {
      toast.error("Wiederherstellung fehlgeschlagen", errorMessage(e));
    }
  };

  const remove = async (b: BackupInfo) => {
    if (!(await confirm({ title: "Backup löschen?", message: b.name, confirmLabel: "Löschen", danger: true }))) return;
    try {
      await api.deleteBackup(b.name);
      list.refetch();
    } catch (e) {
      toast.error("Löschen fehlgeschlagen", errorMessage(e));
    }
  };

  const restart = async () => {
    if (!(await confirm({ title: "MediaCraft neu starten?", message: "Laufende Downloads in den Clients sind nicht betroffen.", confirmLabel: "Neu starten" })))
      return;
    try {
      await api.restart();
      await afterRestart("Neustart ausgelöst");
    } catch (e) {
      toast.error("Neustart fehlgeschlagen", errorMessage(e));
    }
  };

  const s = section.draft as BackupSettings | null;
  return (
    <div className="settings-page">
      <Card
        title="Backups"
        actions={
          <div className="row gap-sm">
            <button className="btn btn-sm" onClick={() => fileRef.current?.click()} disabled={!!busy}>
              <Upload size={14} /> Datei wiederherstellen
            </button>
            <button className="btn btn-sm btn-primary" onClick={create} disabled={!!busy}>
              {busy === "create" ? <Spinner size={14} /> : <Archive size={14} />} Backup jetzt erstellen
            </button>
          </div>
        }
      >
        <input
          ref={fileRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) upload(f);
          }}
        />
        {busy === "restart" && (
          <div className="health-ok">
            <Spinner size={16} /> Warte auf Neustart…
          </div>
        )}
        {list.data?.restore_pending && <p className="tone-text-warning">Eine Wiederherstellung ist vorgemerkt und wird beim nächsten Start angewendet.</p>}
        {list.isLoading && <Loading />}
        {list.error ? <ErrorBox error={list.error} /> : null}
        {list.data && list.data.backups.length === 0 && <Empty title="Noch keine Backups" />}
        {list.data && list.data.backups.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Datei</th>
                  <th>Art</th>
                  <th>Erstellt</th>
                  <th>Größe</th>
                  <th className="w-actions" />
                </tr>
              </thead>
              <tbody>
                {list.data.backups.map((b) => (
                  <tr key={b.name}>
                    <td className="mono small break">{b.name}</td>
                    <td>
                      <Badge tone={b.kind === "manual" ? "accent" : "muted"}>{KIND_LABELS[b.kind] ?? b.kind}</Badge>
                    </td>
                    <td className="small nowrap">{fmtDateTime(b.created)}</td>
                    <td className="small">{fmtSize(b.size)}</td>
                    <td className="actions">
                      <a className="icon-btn" href={api.backupUrl(b.name)} download title="Herunterladen" aria-label={`${b.name} herunterladen`}>
                        <Download size={15} />
                      </a>
                      <button className="icon-btn" title="Wiederherstellen" aria-label={`${b.name} wiederherstellen`} onClick={() => restore(b)} disabled={!!busy}>
                        <RotateCcw size={15} />
                      </button>
                      <button className="icon-btn danger" title="Löschen" aria-label={`${b.name} löschen`} onClick={() => remove(b)} disabled={!!busy}>
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && <p className="muted small">Ordner: {list.data.folder}</p>}
      </Card>

      <Card title="Automatische Backups">
        {section.error ? <ErrorBox error={section.error} /> : null}
        {!s ? (
          <Loading />
        ) : (
          <>
            <div className="form-grid">
              <Field label="Intervall (Tage)" help="0 = keine automatischen Backups">
                <NumberInput value={s.interval_days} onValue={(v) => section.set("interval_days", v)} min={0} />
              </Field>
              <Field label="Aufbewahren (Tage)" help="Ältere automatische Backups werden gelöscht, manuelle bleiben">
                <NumberInput value={s.retention_days} onValue={(v) => section.set("retention_days", v)} min={0} />
              </Field>
            </div>
            <p className="muted small">Vor jedem Update, das die Datenbank ändert, legt MediaCraft zusätzlich automatisch ein Backup an.</p>
            <SaveBar dirty={section.dirty} saving={section.saving} onSave={() => section.save()} onReset={section.reset} />
          </>
        )}
      </Card>

      <Card title="Neustart">
        <p className="muted">Startet den MediaCraft-Prozess neu, z. B. nach einer Wiederherstellung.</p>
        <button className="btn" onClick={restart} disabled={!!busy}>
          <Power size={15} /> MediaCraft neu starten
        </button>
      </Card>
    </div>
  );
}
