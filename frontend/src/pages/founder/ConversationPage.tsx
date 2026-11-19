/**
 * One founder conversation (`/conversations/:id`). It loads the stored conversation and renders it
 * by its state, always by the same rule:
 * - Ready: the tutorial, then the device check, then the call (START).
 * - During a call: the live conversation view with the status and STOPP (call/useCall.ts).
 * - Any other state: the conversation view filled from the database, with its outcome message, and
 *   „Aktualisieren" while it runs elsewhere (another tab).
 * The conversation, live or stored, is one fill page: the title row, the bar and the outcome always
 * stay in view, and only the messages scroll. It is the same view element before and after the call
 * ends, so the reader stays where they were. During the call the title row has no back link,
 * because STOPP is the way out.
 * When a call ends, the page renders the stored conversation the backend returned. If that is Ready
 * again (the start failed, or the connection broke before the founder said anything), the founder
 * is back at the device check with everything passed. If the START request itself fails, the page
 * shows the backend's message and reloads the conversation.
 *
 * The page owns the device setup, the microphone stream included: the device check opens it and the
 * call uses it. It is stopped when the page is left, or once the conversation can no longer start,
 * so a retry after a failed start uses the same working microphone without a new permission.
 */
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api, errorMessage, type ConversationView as StoredConversation } from "../../api/client";
import { useCall } from "../../call/useCall";
import { ConversationView } from "../../conversation/ConversationView";
import { formatDateTime } from "../../format";
import { useConfirm, useNotify } from "../../notifications/NotificationsProvider";
import { DeviceCheck, NO_SETUP, type DeviceSetup } from "./DeviceCheck";
import { Tutorial } from "./Tutorial";

// What the founder reads when a call ends with the conversation Ready again; the same words as the
// backend's message for a START that OpenAI refused.
const START_FAILED = "Das Gespräch konnte nicht starten. Bitte versuchen Sie es erneut.";

export function ConversationPage() {
  const { id = "" } = useParams();
  const notify = useNotify();
  const confirm = useConfirm();
  const [conversation, setConversation] = useState<StoredConversation | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<"tutorial" | "devices">("tutorial");
  const [setup, setSetup] = useState<DeviceSetup>(NO_SETUP);

  const load = useCallback(async () => {
    try {
      setConversation(await api.conversation(id));
      setLoadError(null);
    } catch (failure) {
      setLoadError(errorMessage(failure));
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);

  const call = useCall((ended) => {
    if (!ended) {
      void load(); // the end report failed; the stored conversation says how it ended
      return;
    }
    setConversation(ended);
    if (ended.state === "ready") {
      notify(START_FAILED, "error");
      setStep("devices");
    }
  });

  const changeSetup = useCallback((change: Partial<DeviceSetup>) => setSetup((now) => ({ ...now, ...change })), []);

  // The microphone stream is stopped when it is replaced, when the page is left, and once the
  // conversation can no longer start (it is running or over), so the browser stops recording.
  useEffect(() => () => setup.microphone?.getTracks().forEach((track) => track.stop()), [setup.microphone]);
  const canStart = conversation?.state === "ready";
  useEffect(() => {
    if (conversation && !canStart && call.phase === "idle") changeSetup({ microphone: null });
  }, [conversation, canStart, call.phase, changeSetup]);

  async function startCall() {
    if (!setup.microphone) return;
    try {
      await call.start(id, setup.microphone, setup.speakerId);
    } catch (failure) {
      notify(errorMessage(failure), "error");
      await load(); // Ready: the device check again; started in another tab: the running conversation
    }
  }

  async function stop() {
    const confirmed = await confirm({
      title: "Jetzt beenden?",
      text: "Das Gespräch wird als nicht abgeschlossen gespeichert und kann nicht eingereicht werden.",
      confirmLabel: "Beenden",
      cancelLabel: "Weitersprechen",
      danger: true,
    });
    if (confirmed) call.stop();
  }

  async function refresh() {
    await load();
    notify("Aktualisiert.");
  }

  if (loadError && !conversation) {
    return (
      <section className="card">
        <p className="error">{loadError}</p>
        <button className="button" onClick={() => void load()}>Erneut versuchen</button>
      </section>
    );
  }
  if (!conversation) return null; // loading takes a moment

  const backLink = <Link to="/conversations" className="back-link"><ArrowLeft size={16} aria-hidden /> Meine Gespräche</Link>;
  const inCall = call.phase !== "idle";
  if (canStart && !inCall) {
    return step === "tutorial" ? (
      <>
        <div className="page-head">{backLink}<h1>So läuft das Gespräch</h1></div>
        <Tutorial onDone={() => setStep("devices")} />
      </>
    ) : (
      <>
        <div className="page-head">{backLink}<h1>Gerätetest</h1></div>
        <DeviceCheck setup={setup} onChange={changeSetup} onStart={() => void startCall()} />
      </>
    );
  }

  const date = inCall ? call.startedAt : conversation.started_at ?? conversation.created_at;
  return (
    <div className="page-fill">
      <div className="page-head">
        {!inCall && backLink}
        <h1>Ihr Gespräch</h1>
        {date && <span className="muted">{formatDateTime(date)}</span>}
      </div>
      <div className="fill-area">
        <section className="card card-fill">
          {inCall ? (
            <ConversationView
              messages={call.messages}
              agentName={call.agentName}
              founderLabel="Sie"
              status={call.status}
              toolCalls={call.toolCalls}
              followUpFrom={call.followUpFrom}
              actions={call.canStop && <button className="button button-danger" onClick={() => void stop()}>STOPP</button>}
            />
          ) : (
            <ConversationView
              messages={conversation.transcript}
              agentName={conversation.agent_name}
              founderLabel="Sie"
              outcome={conversation}
              actions={
                conversation.state === "in_progress" && (
                  <button className="button" onClick={() => void refresh()}>Aktualisieren</button>
                )
              }
            />
          )}
        </section>
      </div>
    </div>
  );
}
