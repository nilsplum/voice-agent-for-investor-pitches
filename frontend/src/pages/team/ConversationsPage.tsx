/**
 * „Gespräche", the team's start page: every conversation, newest first, with its founder, company
 * and state. The backend returns all of them at once (read from the database, no live updates), and
 * search and filter apply here in the browser while typing. Clicking a company name searches for
 * it, which shows all of its conversations; clicking a row opens the conversation's details. A fill
 * page: the title and the filters stay in view, and only the table scrolls, below its header row.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, errorMessage, type ConversationState, type TeamConversationRow } from "../../api/client";
import { formatDateTime } from "../../format";
import { CONVERSATION_STATE_LABELS } from "../../labels";

const STATES = Object.keys(CONVERSATION_STATE_LABELS) as ConversationState[];

export function ConversationsPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<TeamConversationRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<ConversationState | "">("");

  useEffect(() => {
    api.teamConversations().then(setConversations, (failure: unknown) => setLoadError(errorMessage(failure)));
  }, []);

  const query = search.trim().toLowerCase();
  const shown = (conversations ?? []).filter(
    (row) =>
      (!state || row.state === state) &&
      [row.founder_name, row.founder_email, row.company_name].some((value) => value.toLowerCase().includes(query)),
  );

  return (
    <div className="page-fill">
      <h1>Gespräche</h1>
      <div className="fill-area">
        <section className="card card-fill">
          <div className="filters">
            <label className="field filter-search">
              Suche
              <input
                type="search"
                placeholder="Nach Gründer, E-Mail oder Firma suchen"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className="field">
              Status
              <select value={state} onChange={(event) => setState(event.target.value as ConversationState | "")}>
                <option value="">Alle Status</option>
                {STATES.map((value) => (
                  <option key={value} value={value}>{CONVERSATION_STATE_LABELS[value]}</option>
                ))}
              </select>
            </label>
          </div>
          {loadError && <p className="error">{loadError}</p>}
          {conversations && shown.length === 0 && <p className="muted">Keine passenden Gespräche.</p>}
          {shown.length > 0 && (
            <div className="scroll-pane">
              <table>
                <thead>
                  <tr><th>Datum</th><th>Gründer</th><th>Firma</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {shown.map((row) => (
                    <tr key={row.id} className="row-link" onClick={() => navigate(`/team/conversations/${row.id}`)}>
                      <td>
                        <Link to={`/team/conversations/${row.id}`} onClick={(event) => event.stopPropagation()}>
                          {formatDateTime(row.started_at ?? row.created_at)}
                        </Link>
                      </td>
                      <td>
                        {row.founder_name}
                        <span className="cell-detail">{row.founder_email}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          title="Alle Gespräche dieser Firma"
                          onClick={(event) => {
                            event.stopPropagation(); // searches for the company instead of opening the row
                            setSearch(row.company_name);
                          }}
                        >
                          {row.company_name}
                        </button>
                      </td>
                      <td><span className={`badge badge-${row.state}`}>{CONVERSATION_STATE_LABELS[row.state]}</span></td>
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
