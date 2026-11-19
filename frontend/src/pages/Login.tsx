/**
 * The one login page for founders and the team: the backend tells them apart by the email. On
 * success the guest-page guard in App.tsx takes the user to their role's start page.
 */
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "../api/client";
import { useApp } from "../AppProvider";

export function Login() {
  const { setMe } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setMe(await api.login({ email, password }));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card form-card">
      <h1>Anmelden</h1>
      <form className="form" onSubmit={submit}>
        <label className="field">
          E-Mail<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field">
          Passwort
          <input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button button-primary" disabled={busy}>Anmelden</button>
      </form>
      <p className="muted">Noch kein Konto? <Link to="/signup">Registrieren</Link></p>
    </section>
  );
}
