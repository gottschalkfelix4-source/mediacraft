import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Eye, EyeOff, RefreshCw, ShieldCheck, Link2 } from "lucide-react";
import { api, errorMessage } from "../../api";
import { ErrorBox, Field, Loading, Select, TextInput, Toggle } from "../../components/ui";
import { useConfirm } from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { SaveBar, Section, useSection } from "./common";
import type { AuthSettings, UiSettings } from "../../types";

function CopyField({ value, secret }: { value: string; secret?: boolean }) {
  const [show, setShow] = useState(!secret);
  const toast = useToast();
  return (
    <div className="row gap-sm">
      <input className="input mono grow" readOnly value={show ? value : "•".repeat(Math.min(32, value.length))} onFocus={(e) => show && e.target.select()} />
      {secret && (
        <button className="icon-btn" onClick={() => setShow(!show)} title={show ? "Verbergen" : "Anzeigen"} aria-label="Anzeigen umschalten">
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      )}
      <button
        className="icon-btn"
        title="Kopieren"
        aria-label="Kopieren"
        onClick={() =>
          navigator.clipboard?.writeText(value).then(
            () => toast.success("In die Zwischenablage kopiert"),
            () => toast.error("Kopieren nicht möglich"),
          )
        }
      >
        <Copy size={16} />
      </button>
    </div>
  );
}

export function GeneralSettings() {
  const auth = useSection("auth");
  const ui = useSection("ui");
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();

  if (auth.error || ui.error) return <ErrorBox error={auth.error ?? ui.error} />;
  if (!auth.draft || !ui.draft) return <Loading />;
  const a = auth.draft as AuthSettings;
  const u = ui.draft as UiSettings;
  const origin = window.location.origin;
  const apiKey = status.data?.api_key ?? "";
  const pwMismatch = password !== password2;
  const dirty = auth.dirty || ui.dirty || password.length > 0;

  const regenerate = async () => {
    if (!(await confirm({ title: "API-Key neu erzeugen?", message: "Alle angebundenen Apps (Jellyseerr, Prowlarr, Homepage …) müssen danach mit dem neuen Key konfiguriert werden.", confirmLabel: "Neu erzeugen", danger: true }))) return;
    try {
      await api.regenerateApiKey();
      qc.invalidateQueries({ queryKey: ["status"] });
      toast.success("Neuer API-Key erzeugt");
    } catch (e) {
      toast.error("Fehlgeschlagen", errorMessage(e));
    }
  };

  return (
    <div className="settings-page">
      <Section
        title="Sicherheit"
        help="Mit „Formular-Anmeldung“ ist die Weboberfläche passwortgeschützt. Der API-Key funktioniert unabhängig davon. Nach 5 Fehlversuchen wird eine Adresse für 15 Minuten gesperrt."
      >
        <div className="form-grid">
          <Field label="Authentifizierung">
            <Select
              value={a.method}
              onValue={(v) => auth.set("method", v)}
              options={[
                { value: "none", label: "Keine (nur im vertrauenswürdigen Netz!)" },
                { value: "forms", label: "Formular-Anmeldung" },
              ]}
            />
          </Field>
          <Field label="Benutzername">
            <TextInput value={a.username} onValue={(v) => auth.set("username", v)} autoComplete="username" disabled={a.method === "none"} />
          </Field>
          <Field label="Neues Passwort" help="Leer lassen, um das bestehende zu behalten">
            <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={a.method === "none"} />
          </Field>
          <Field label="Passwort wiederholen" help={pwMismatch && password2 ? <span className="tone-text-danger">Passwörter stimmen nicht überein</span> : undefined}>
            <input className="input" type="password" autoComplete="new-password" value={password2} onChange={(e) => setPassword2(e.target.value)} disabled={a.method === "none"} />
          </Field>
        </div>
        <Toggle
          checked={!!a.local_bypass}
          onChange={(v) => auth.set("local_bypass", v)}
          disabled={a.method === "none"}
          label="Für lokale Adressen keine Anmeldung verlangen"
          title="Gilt nur für direkte Zugriffe aus dem Heimnetz. Über einen Reverse-Proxy ist die Anmeldung immer nötig."
        />
      </Section>

      <Section
        title="API-Key"
        actions={
          <button className="btn btn-danger-outline" onClick={regenerate}>
            <RefreshCw size={15} /> Neu erzeugen
          </button>
        }
      >
        {status.isLoading ? <Loading /> : <CopyField value={apiKey} secret />}
      </Section>

      <Section title="Integrationen" help="MediaCraft spricht eine Teilmenge der Sonarr-/Radarr-v3-API. So lässt es sich in Jellyseerr/Overseerr, Prowlarr (Indexer-Sync) und Homepage-Widgets einbinden – jeweils mit demselben API-Key.">
        <div className="integrations">
          <div className="integration">
            <h4>
              <Link2 size={15} /> Sonarr-kompatibel (Serien)
            </h4>
            <CopyField value={`${origin}/sonarr`} />
            <p className="muted small">In Jellyseerr/Overseerr als Sonarr-Server, in Prowlarr als „Sonarr“-App, in Homepage als sonarr-Widget eintragen.</p>
          </div>
          <div className="integration">
            <h4>
              <Link2 size={15} /> Radarr-kompatibel (Filme)
            </h4>
            <CopyField value={`${origin}/radarr`} />
            <p className="muted small">In Jellyseerr/Overseerr als Radarr-Server, in Prowlarr als „Radarr“-App, in Homepage als radarr-Widget eintragen.</p>
          </div>
          <div className="integration">
            <h4>
              <ShieldCheck size={15} /> API-Key
            </h4>
            <CopyField value={apiKey} secret />
            <p className="muted small">Für alle Integrationen identisch. Eigene API: Header <code>X-Api-Key</code> oder Parameter <code>?apikey=</code>.</p>
          </div>
          <div className="integration">
            <h4>
              <Link2 size={15} /> iCal-Feed
            </h4>
            <CopyField value={`${origin}/api/v1/feed/calendar.ics?apikey=${apiKey}`} secret />
          </div>
        </div>
      </Section>

      <Section title="Oberfläche">
        <div className="form-grid">
          <Field label="Erster Wochentag (Kalender)">
            <Select
              value={u.first_day_of_week}
              onValue={(v) => ui.set("first_day_of_week", v)}
              options={[
                { value: 1, label: "Montag" },
                { value: 0, label: "Sonntag" },
                { value: 6, label: "Samstag" },
              ]}
            />
          </Field>
          <Field label="Sprache">
            <Select value={u.language} onValue={(v) => ui.set("language", v)} options={[{ value: "de", label: "Deutsch" }]} />
          </Field>
        </div>
        <p className="muted small">Das Farbschema (hell/dunkel) wird pro Browser über das Symbol oben rechts gewählt.</p>
      </Section>

      <SaveBar
        dirty={dirty}
        saving={auth.saving || ui.saving}
        onSave={async () => {
          if (password && pwMismatch) {
            toast.error("Passwörter stimmen nicht überein");
            return;
          }
          if (auth.dirty || password) {
            const ok = await auth.save(password ? { password } : undefined);
            if (ok) {
              setPassword("");
              setPassword2("");
              qc.invalidateQueries({ queryKey: ["auth"] });
            }
          }
          if (ui.dirty) await ui.save();
        }}
        onReset={() => {
          auth.reset();
          ui.reset();
          setPassword("");
          setPassword2("");
        }}
      />
    </div>
  );
}
