import { useState } from "react";
import { LogIn } from "lucide-react";
import { api, errorMessage } from "../api";
import { Spinner } from "../components/ui";

export function Login({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.login(username, password, remember);
      onDone();
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-login">
          <div className="brand-logo">M</div>
          <div className="brand-text">MediaCraft</div>
        </div>
        <p className="muted">Bitte anmelden</p>
        <label className="field-label" htmlFor="login-user">
          Benutzername
        </label>
        <input id="login-user" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        <label className="field-label" htmlFor="login-pw">
          Passwort
        </label>
        <input id="login-pw" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <label className="checkbox">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Angemeldet bleiben (30 Tage)
        </label>
        {err && <div className="alert alert-error">{err}</div>}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {busy ? <Spinner size={16} /> : <LogIn size={16} />} Anmelden
        </button>
      </form>
    </div>
  );
}
