/**
 * „Zugangscodes": the team creates a code for a founder's email and sees every code with its state,
 * newest first; a used code links to the conversation it unlocked. The plain code is shown only once,
 * right after it was created, because the backend stores only its hash; the team copies it and sends
 * it to the founder itself. A fill page: the form and a new code stay in view, and only the list
 * scrolls.
 */
import { Copy } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, errorMessage, type AccessCodeRow, type CreatedAccessCode } from "../../api/client";
import { useApp } from "../../AppProvider";
import { formatDateTime } from "../../format";
import { ACCESS_CODE_STATE_LABELS } from "../../labels";
import { useNotify } from "../../notifications/NotificationsProvider";

export function AccessCodesPage() {
  const { appConfig } = useApp();
  const notify = useNotify();
  const [codes, setCodes] = useState<AccessCodeRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [created, setCreated] = useState<CreatedAccessCode | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.accessCodes().then(
      (loaded) => {
        setCodes(loaded);
        setLoadError(null);
      },
      (failure: unknown) => setLoadError(errorMessage(failure)),
    );
  }, []);
  useEffect(load, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setCreateError(null);
    try {
      setCreated(await api.createAccessCode(email));
      setEmail("");
      load();
    } catch (failure) {
      setCreateError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      notify("Code kopiert.");
    } catch {
      notify("Kopieren hat nicht geklappt. Bitte kopieren Sie den Code selbst.", "error");
    }
  }

  return (
    <div className="page-fill">
      <h1>Zugangscodes</h1>
      <section className="card">
        <h2>Code erstellen</h2>
        <form className="form-inline" onSubmit={create}>
          <label className="field">
            E-Mail<input required type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <button className="button button-primary" disabled={busy}>Erstellen</button>
        </form>
        {createError && <p className="error" role="alert">{createError}</p>}
        {created && (
          <div className="code-box">
            <p className="muted">Zugangscode für {created.email}</p>
            <div className="code-row">
              <code className="code">{created.code}</code>
              <button className="button" onClick={() => copy(created.code)}>
                <Copy size={16} aria-hidden /> Kopieren
              </button>
            </div>
            <p>
              Senden Sie diesen Code an die angegebene E-Mail-Adresse. Er wird nur jetzt angezeigt und ist{" "}
              {appConfig.access_code_valid_hours} Stunden gültig.
            </p>
          </div>
        )}
      </section>
      <div className="fill-area">
        <section className="card card-fill">
          {loadError && <p className="error">{loadError}</p>}
          {codes?.length === 0 && <p className="muted">Noch keine Zugangscodes.</p>}
          {codes && codes.length > 0 && (
            <div className="scroll-pane">
              <table>
                <thead>
                  <tr><th>E-Mail</th><th>Erstellt</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {codes.map((code) => (
                    <tr key={code.id}>
                      <td>{code.email}</td>
                      <td>{formatDateTime(code.created_at)}</td>
                      <td>
                        {code.state === "used" && code.conversation_id ? (
                          <Link to={`/team/conversations/${code.conversation_id}`} className="badge badge-used badge-link">
                            {ACCESS_CODE_STATE_LABELS.used}
                          </Link>
                        ) : (
                          <span className={`badge badge-${code.state}`}>
                            {code.state === "unused"
                              ? `${ACCESS_CODE_STATE_LABELS.unused}, gültig bis ${formatDateTime(code.expires_at)}`
                              : ACCESS_CODE_STATE_LABELS[code.state]}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
