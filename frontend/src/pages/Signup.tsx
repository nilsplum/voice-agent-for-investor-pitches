/**
 * Founder signup with the access code from the team. One request creates the account and the first
 * conversation together, or nothing at all (a rejected code). On success the founder is logged in
 * and goes straight into the new conversation. On an error the form keeps its values and shows the
 * backend's message.
 */
import { startTransition, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api, errorMessage, type SignupRequest } from "../api/client";
import { useApp } from "../AppProvider";

export function Signup() {
  const { setMe } = useApp();
  const navigate = useNavigate();
  const [form, setForm] = useState<SignupRequest>({ name: "", email: "", password: "", company_name: "", code: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { me, conversation_id } = await api.signup(form);
      // One transition for the login and the new address (the router applies its navigations as
      // transitions): the guest-page guard in App.tsx must never see the login on the signup page,
      // or it would send the founder to the list instead of the new conversation.
      startTransition(() => {
        setMe(me);
        navigate(`/conversations/${conversation_id}`);
      });
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  const bind = (key: keyof SignupRequest) => ({
    value: form[key],
    onChange: (event: { target: { value: string } }) => setForm((current) => ({ ...current, [key]: event.target.value })),
  });

  return (
    <section className="card form-card">
      <h1>Registrieren</h1>
      <form className="form" onSubmit={submit}>
        <label className="field">Name<input required autoComplete="name" {...bind("name")} /></label>
        <label className="field">E-Mail<input required type="email" autoComplete="email" {...bind("email")} /></label>
        <label className="field">Passwort<input required type="password" autoComplete="new-password" {...bind("password")} /></label>
        <label className="field">Firmenname<input required autoComplete="organization" {...bind("company_name")} /></label>
        <label className="field">
          Zugangscode<input required autoComplete="off" spellCheck={false} className="input-code" {...bind("code")} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button button-primary" disabled={busy}>Registrieren</button>
      </form>
      <p className="muted">Schon registriert? <Link to="/login">Anmelden</Link></p>
    </section>
  );
}
