/**
 * „Meine Gespräche": unlocking a further conversation with a new access code („Neues Gespräch"),
 * and the founder's conversations, newest first; each opens in the conversation page. Unlocking goes
 * through the same redemption step on the backend as the signup, and like the signup it leads
 * straight into the new conversation. A fill page: „Neues Gespräch" stays in view, and only the
 * list scrolls.
 */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api, errorMessage, type ConversationSummary } from "../../api/client";
import { formatDateTime } from "../../format";
import { CONVERSATION_STATE_LABELS } from "../../labels";
import { useNotify } from "../../notifications/NotificationsProvider";

export function ConversationsPage() {
  const notify = useNotify();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.myConversations().then(
      (loaded) => {
        setConversations(loaded);
        setLoadError(null);
      },
      (failure: unknown) => setLoadError(errorMessage(failure)),
    );
  }, []);
  useEffect(load, [load]);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setUnlockError(null);
    try {
      const unlocked = await api.unlockConversation(code);
      notify("Gespräch freigeschaltet.");
      navigate(`/conversations/${unlocked.id}`);
    } catch (failure) {
      setUnlockError(errorMessage(failure));
      setBusy(false);
    }
  }

  return (
    <div className="page-fill">
      <h1>Meine Gespräche</h1>
      <section className="card">
        <h2>Neues Gespräch</h2>
        <form className="form-inline" onSubmit={unlock}>
          <label className="field">
            Zugangscode
            <input required autoComplete="off" spellCheck={false} className="input-code" value={code} onChange={(event) => setCode(event.target.value)} />
          </label>
          <button className="button button-primary" disabled={busy}>Gespräch freischalten</button>
        </form>
        {unlockError && <p className="error" role="alert">{unlockError}</p>}
      </section>
      <div className="fill-area">
        <section className="card card-fill">
          {loadError && <p className="error">{loadError}</p>}
          {conversations?.length === 0 && <p className="muted">Noch keine Gespräche.</p>}
          {conversations && conversations.length > 0 && (
            <ul className="list scroll-pane">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <Link to={`/conversations/${conversation.id}`} className="list-row list-link">
                    <span>{formatDateTime(conversation.started_at ?? conversation.created_at)}</span>
                    <span className={`badge badge-${conversation.state}`}>{CONVERSATION_STATE_LABELS[conversation.state]}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
