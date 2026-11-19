/**
 * „Gesprächsdetails" for the team (ConversationDetailCards.tsx), most relevant first: the facts
 * (the conversation's state and times, the founder, the settings used) side by side, then the
 * questionnaire, then the founder's conversation view exactly as the founder sees it (the founder's
 * name instead of „Sie"), collapsed until opened. Everything is read from the database;
 * „Aktualisieren" reloads it, also while the conversation runs, which shows the messages saved so
 * far and, after the first submit, the answers. There are no live updates: the live stream exists
 * only in the founder's own call connection.
 */
import { ArrowLeft, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api, errorMessage, type SettingsPage, type TeamConversationDetail } from "../../api/client";
import { useNotify } from "../../notifications/NotificationsProvider";
import { ConversationFactsCard, FounderCard, QuestionnaireCard, SettingsCard, TranscriptCard } from "./ConversationDetailCards";

export function ConversationDetailPage() {
  const { id = "" } = useParams();
  const notify = useNotify();
  const [detail, setDetail] = useState<TeamConversationDetail | null>(null);
  const [options, setOptions] = useState<SettingsPage | null>(null); // only for the settings' labels
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await api.teamConversation(id));
      setLoadError(null);
      return true;
    } catch (failure) {
      setLoadError(errorMessage(failure));
      return false;
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    // Without the labels the settings card shows the stored values themselves.
    api.settings().then(setOptions, () => undefined);
  }, []);

  async function refresh() {
    if (await load()) notify("Aktualisiert.");
  }

  return (
    <>
      <div className="page-head">
        <Link to="/team/conversations" className="back-link"><ArrowLeft size={16} aria-hidden /> Zurück zu den Gesprächen</Link>
        <h1>Gesprächsdetails</h1>
        <button className="button page-head-action" onClick={() => void refresh()}>
          <RefreshCw size={16} aria-hidden /> Aktualisieren
        </button>
      </div>
      {loadError && <p className="error card-error">{loadError}</p>}
      {detail && (
        <>
          <div className="detail-facts">
            <ConversationFactsCard view={detail.view} />
            <FounderCard detail={detail} />
            <SettingsCard settings={detail.settings} options={options} />
          </div>
          <QuestionnaireCard questionnaire={detail.questionnaire} />
          <TranscriptCard detail={detail} />
        </>
      )}
    </>
  );
}
