/**
 * The cards of a conversation's details for the team, in the page's order: the facts „Gespräch"
 * (state, reason and times), „Gründer" and „Verwendete Einstellungen" (the copy the conversation
 * made at START); „Fragebogen" (the "not reviewed" note and the summary, then every question with
 * its answer, the reviewer's follow-up with its reason and what came up in the follow-up round);
 * and „Gesprächsverlauf", the founder's own conversation view in a collapsible card. Whatever does
 * not exist yet shows „Noch nicht verfügbar"; a question still without an answer once everything is
 * written down (the founder ended early) shows „Nicht beantwortet". The settings' values are labelled
 * with the options the settings page gets from the backend, so the labels stay in the config module.
 */
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import type { ConversationView as StoredConversation, Option, Questionnaire, Settings, SettingsPage, TeamConversationDetail } from "../../api/client";
import { ConversationView } from "../../conversation/ConversationView";
import { formatDateTime } from "../../format";
import { CONVERSATION_STATE_LABELS, END_REASON_TEXTS } from "../../labels";

const NOT_AVAILABLE = "Noch nicht verfügbar";
const NOT_ANSWERED = "Nicht beantwortet";

function Facts({ facts }: { facts: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {facts.map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const time = (iso: string | null) => (iso ? formatDateTime(iso) : NOT_AVAILABLE);

export function FounderCard({ detail }: { detail: TeamConversationDetail }) {
  return (
    <section className="card">
      <h2>Gründer</h2>
      <Facts facts={[["Name", detail.founder_name], ["E-Mail", detail.founder_email], ["Firma", detail.company_name]]} />
    </section>
  );
}

function StateBadge({ view }: { view: StoredConversation }) {
  return <span className={`badge badge-${view.state}`}>{CONVERSATION_STATE_LABELS[view.state]}</span>;
}

export function ConversationFactsCard({ view }: { view: StoredConversation }) {
  const facts: [string, ReactNode][] = [["Status", <StateBadge view={view} />]];
  if (view.end_reason) facts.push(["Grund", END_REASON_TEXTS[view.end_reason]]);
  facts.push(["Erstellt", formatDateTime(view.created_at)], ["Gestartet", time(view.started_at)],
             ["Beendet", time(view.ended_at)]);
  return (
    <section className="card">
      <h2>Gespräch</h2>
      <Facts facts={facts} />
    </section>
  );
}

export function QuestionnaireCard({ questionnaire }: { questionnaire: Questionnaire | null }) {
  return (
    <section className="card">
      <h2>Fragebogen</h2>
      {!questionnaire ? (
        <p className="muted">{NOT_AVAILABLE}</p>
      ) : (
        <>
          {questionnaire.reviewed === false && (
            <p className="note">Nicht geprüft: Die automatische Prüfung ist fehlgeschlagen, deshalb gab es keine Rückfragerunde.</p>
          )}
          <h3>Zusammenfassung</h3>
          <p className={questionnaire.summary ? "prose" : "muted"}>{questionnaire.summary ?? NOT_AVAILABLE}</p>
          <ol className="questionnaire scroll-pane">
            {questionnaire.entries.map((entry) => (
              <li key={entry.id}>
                <h3>{entry.topic}</h3>
                <p className="muted">{entry.question}</p>
                <p className={entry.answer ? "prose" : "muted"}>
                  {entry.answer ?? (questionnaire.summary ? NOT_ANSWERED : NOT_AVAILABLE)}
                </p>
                {entry.follow_up && (
                  <div className="follow-up">
                    <p><strong>Rückfrage:</strong> {entry.follow_up.question}</p>
                    <p><strong>Begründung:</strong> {entry.follow_up.explanation}</p>
                  </div>
                )}
                {entry.follow_up_answer && (
                  <p className="prose"><strong>Aus der Rückfragerunde:</strong> {entry.follow_up_answer}</p>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/** The German label of a stored value; the value itself if it is no longer offered. */
function labelOf(options: Option[] | undefined, value: string): string {
  return options?.find((option) => option.value === value)?.label ?? value;
}

export function SettingsCard({ settings, options }: { settings: Settings | null; options: SettingsPage | null }) {
  return (
    <section className="card">
      <h2>Verwendete Einstellungen</h2>
      {!settings ? (
        <p className="muted">{NOT_AVAILABLE}</p>
      ) : (
        <Facts
          facts={[
            ["Name des Agenten", settings.agent_name],
            ["Gesprächssprache", labelOf(options?.languages, settings.language)],
            ["Protokollant: Modell", labelOf(options?.models, settings.note_taker_model)],
            ["Protokollant: Denkstufe", labelOf(options?.thinking_levels, settings.note_taker_thinking)],
            ["Prüfer: Modell", labelOf(options?.models, settings.reviewer_model)],
            ["Prüfer: Denkstufe", labelOf(options?.thinking_levels, settings.reviewer_thinking)],
          ]}
        />
      )}
    </section>
  );
}

/** The founder's own conversation view (transcript and outcome message), closed until the team
 * opens it, so the facts and the questionnaire come first. React keeps the element across
 * „Aktualisieren", so an opened card stays open. */
export function TranscriptCard({ detail }: { detail: TeamConversationDetail }) {
  const count = detail.view.transcript.length;
  return (
    <details className="card collapsible">
      <summary>
        <ChevronRight className="collapsible-chevron" size={18} aria-hidden />
        <h2>Gesprächsverlauf</h2>
        <StateBadge view={detail.view} />
        <span className="muted">{count === 1 ? "1 Nachricht" : `${count} Nachrichten`}</span>
      </summary>
      <ConversationView
        messages={detail.view.transcript}
        agentName={detail.view.agent_name}
        founderLabel={detail.founder_name}
        outcome={detail.view}
      />
    </details>
  );
}
