/**
 * The outcome message below the last message of the conversation view: one thing per state, the
 * same for the founder (live and later) and the team. Completed: the success message with the
 * summary behind „Zusammenfassung anzeigen"; Unfinished: why it ended and that a new attempt needs a
 * new code, never a summary; In progress: that it is running right now; Ready: nothing.
 */
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { useId, useState } from "react";
import type { ConversationView } from "../api/client";
import { END_REASON_TEXTS } from "../labels";

export function OutcomeMessage({ view }: { view: ConversationView }) {
  const [showSummary, setShowSummary] = useState(false);
  const summaryId = useId();

  switch (view.state) {
    case "completed":
      return (
        <div className="outcome outcome-completed">
          <p className="outcome-title"><CircleCheck size={20} aria-hidden /> Vielen Dank, Ihr Gespräch ist abgeschlossen.</p>
          {view.summary && (
            <>
              <button
                className="button button-primary"
                aria-expanded={showSummary}
                aria-controls={summaryId}
                onClick={() => setShowSummary(!showSummary)}
              >
                {showSummary ? "Zusammenfassung ausblenden" : "Zusammenfassung anzeigen"}
              </button>
              {showSummary && <p id={summaryId} className="outcome-summary">{view.summary}</p>}
            </>
          )}
          <p>Das Team prüft Ihre Antworten und meldet sich bei Ihnen.</p>
        </div>
      );
    case "unfinished":
      return (
        <div className="outcome outcome-unfinished">
          <p className="outcome-title"><CircleAlert size={20} aria-hidden /> Dieses Gespräch wurde vor dem Abschluss beendet.</p>
          {view.end_reason && <p>{END_REASON_TEXTS[view.end_reason]}</p>}
          <p>
            Die Antworten konnten nicht eingereicht werden. Für einen neuen Versuch ist ein neuer Zugangscode vom Team
            nötig.
          </p>
        </div>
      );
    case "in_progress":
      return (
        <div className="outcome outcome-in_progress">
          <p className="outcome-title"><LoaderCircle size={20} aria-hidden /> Dieses Gespräch läuft gerade.</p>
        </div>
      );
    case "ready":
      return null;
  }
}
