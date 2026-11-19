/**
 * The device check before every conversation: three rows (connection, microphone, speaker), each
 * with its state and, on a problem, a short fix. START is enabled once all three passed.
 *
 * - Verbindung: our server (GET /api/app-config) and OpenAI (a no-cors request whose answer the
 *   browser never sees; any answer proves the network path), each with the configured timeout.
 * - Mikrofon: opens the microphone, lists the microphones (switching reopens the stream) and shows
 *   its level, measured like the agent's „Spricht" (audio/useAudioLevel.ts).
 * - Lautsprecher: a speaker choice where the browser allows it, and a test tone played on the same
 *   path as the agent's voice (audio/speaker.ts), which the founder confirms.
 *
 * The page owns the results (`DeviceSetup`: the microphone stream, the chosen speaker and the passed
 * checks), so after a failed start the founder is back here with everything passed and the same
 * microphone. This component only runs the checks.
 */
import { CircleAlert, CircleCheck, Circle, LoaderCircle, Mic, Volume2, Wifi, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../../api/client";
import { useApp } from "../../AppProvider";
import { CAN_CHOOSE_SPEAKER, playTestTone } from "../../audio/speaker";
import { useAudioLevel } from "../../audio/useAudioLevel";

export type DeviceSetup = {
  microphone: MediaStream | null; // open once the founder allowed it; the row has passed then
  speakerId: string; // "" is the browser's default speaker
  connectionPassed: boolean;
  speakerPassed: boolean; // the founder heard the test tone on this speaker
};

export const NO_SETUP: DeviceSetup = { microphone: null, speakerId: "", connectionPassed: false, speakerPassed: false };

type RowState = "open" | "checking" | "passed" | "problem";

const ROW_ICONS: Record<RowState, LucideIcon> = { open: Circle, checking: LoaderCircle, passed: CircleCheck, problem: CircleAlert };

// The microphone meter shows speech (an RMS of about 0.05 to 0.2) across most of its width.
const METER_GAIN = 5;

type Props = {
  setup: DeviceSetup;
  onChange: (change: Partial<DeviceSetup>) => void;
  onStart: () => void; // the page switches to the call at once, so START is pressed only once
};

export function DeviceCheck({ setup, onChange, onStart }: Props) {
  const { appConfig } = useApp();
  const [connection, setConnection] = useState<"checking" | "server" | "openai" | null>(null);
  const [microphoneProblem, setMicrophoneProblem] = useState<"blocked" | "failed" | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [tonePlayed, setTonePlayed] = useState(false);
  const [notHeard, setNotHeard] = useState(false);
  const level = useAudioLevel(setup.microphone);

  const checkConnection = useCallback(async () => {
    setConnection("checking");
    const timeout = () => AbortSignal.timeout(appConfig.connection_check_timeout_ms);
    const [server, openai] = await Promise.all([
      api.appConfig(timeout()).then(() => true, () => false),
      fetch(appConfig.openai_reachability_url, { mode: "no-cors", cache: "no-store", signal: timeout() }).then(
        () => true,
        () => false,
      ),
    ]);
    setConnection(!server ? "server" : !openai ? "openai" : null);
    if (server && openai) onChange({ connectionPassed: true });
  }, [appConfig, onChange]);

  // The connection is checked once on arrival (hence no dependencies); a check that passed before a
  // failed start is kept.
  useEffect(() => {
    if (!setup.connectionPassed) void checkConnection();
  }, []);

  // Device names are only listed once the microphone is allowed; plugging a device in or out
  // updates the lists.
  const listDevices = useCallback(async () => {
    setDevices(await navigator.mediaDevices.enumerateDevices());
  }, []);
  useEffect(() => {
    void listDevices();
    navigator.mediaDevices.addEventListener("devicechange", listDevices);
    return () => navigator.mediaDevices.removeEventListener("devicechange", listDevices);
  }, [listDevices, setup.microphone]);

  async function openMicrophone(deviceId?: string) {
    setMicrophoneProblem(null);
    try {
      const microphone = await navigator.mediaDevices.getUserMedia({
        // The browser's own echo cancellation and noise suppression let laptop speakers work too.
        audio: { deviceId: deviceId ? { exact: deviceId } : undefined, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      onChange({ microphone }); // the page stops the stream it replaces
    } catch (error) {
      setMicrophoneProblem(error instanceof DOMException && error.name === "NotAllowedError" ? "blocked" : "failed");
    }
  }

  function testSpeaker() {
    playTestTone(setup.speakerId);
    setTonePlayed(true);
    setNotHeard(false);
  }

  const microphones = devices.filter((device) => device.kind === "audioinput" && device.deviceId);
  const speakers = devices.filter((device) => device.kind === "audiooutput" && device.deviceId);
  const microphoneId = setup.microphone?.getAudioTracks()[0]?.getSettings().deviceId ?? "";
  const connectionState: RowState = setup.connectionPassed ? "passed" : connection === "checking" ? "checking" : connection ? "problem" : "open";
  const allPassed = setup.connectionPassed && setup.microphone !== null && setup.speakerPassed;

  return (
    <section className="card device-check">
      <CheckRow icon={Wifi} title="Verbindung" state={connectionState}>
        {connection === "server" && <p className="error">Unser Server ist nicht erreichbar.</p>}
        {connection === "openai" && (
          <p className="error">OpenAI ist nicht erreichbar. Bitte prüfen Sie Ihre Internetverbindung oder Firewall.</p>
        )}
        {(connection === "server" || connection === "openai") && (
          <button className="button button-small" onClick={() => void checkConnection()}>Erneut prüfen</button>
        )}
      </CheckRow>

      <CheckRow icon={Mic} title="Mikrofon" state={setup.microphone ? "passed" : microphoneProblem ? "problem" : "open"}>
        {!setup.microphone && !microphoneProblem && (
          <button className="button button-small" onClick={() => void openMicrophone()}>Mikrofon erlauben</button>
        )}
        {microphoneProblem && (
          <>
            <p className="error">
              {microphoneProblem === "blocked"
                ? "Ihr Browser hat das Mikrofon blockiert. Klicken Sie auf das Symbol neben der Adressleiste, erlauben Sie das Mikrofon und versuchen Sie es erneut."
                : "Das Mikrofon ließ sich nicht öffnen. Bitte prüfen Sie, ob eines angeschlossen ist und kein anderes Programm es nutzt."}
            </p>
            <button className="button button-small" onClick={() => void openMicrophone()}>Erneut versuchen</button>
          </>
        )}
        {setup.microphone && (
          <>
            {microphones.length > 1 && (
              <label className="field">
                Mikrofon wählen
                <select value={microphoneId} onChange={(event) => void openMicrophone(event.target.value)}>
                  {microphones.map((device, index) => (
                    <option key={device.deviceId} value={device.deviceId}>{device.label || `Mikrofon ${index + 1}`}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="meter" role="meter" aria-label="Mikrofonpegel" aria-valuemin={0} aria-valuemax={1} aria-valuenow={Math.min(1, level * METER_GAIN)}>
              <div className="meter-fill" style={{ width: `${Math.min(100, level * METER_GAIN * 100)}%` }} />
            </div>
            <p className="muted">Sprechen Sie, um Ihr Mikrofon zu testen.</p>
          </>
        )}
      </CheckRow>

      <CheckRow icon={Volume2} title="Lautsprecher" state={setup.speakerPassed ? "passed" : notHeard ? "problem" : "open"}>
        {CAN_CHOOSE_SPEAKER && speakers.length > 0 ? (
          <label className="field">
            Lautsprecher wählen
            <select
              value={setup.speakerId || speakers[0].deviceId}
              onChange={(event) => {
                onChange({ speakerId: event.target.value, speakerPassed: false }); // a new speaker needs a new test
                setTonePlayed(false);
              }}
            >
              {speakers.map((device, index) => (
                <option key={device.deviceId} value={device.deviceId}>{device.label || `Lautsprecher ${index + 1}`}</option>
              ))}
            </select>
          </label>
        ) : (
          !CAN_CHOOSE_SPEAKER && (
            <p className="muted">Ihr Browser nutzt den Standardlautsprecher. In Chrome können Sie einen auswählen.</p>
          )
        )}
        <div className="row-actions">
          <button className="button button-small" onClick={testSpeaker}>Testton abspielen</button>
          {tonePlayed && !setup.speakerPassed && (
            <>
              <button className="button button-small" onClick={() => onChange({ speakerPassed: true })}>Ich habe ihn gehört</button>
              <button className="button button-small" onClick={() => setNotHeard(true)}>Ich habe nichts gehört</button>
            </>
          )}
        </div>
        {notHeard && !setup.speakerPassed && (
          <p className="error">
            Prüfen Sie die Lautstärke und den gewählten Lautsprecher und spielen Sie den Ton noch einmal ab.
          </p>
        )}
      </CheckRow>

      <div className="actions">
        <button className="button button-primary button-large" disabled={!allPassed} onClick={onStart}>
          START
        </button>
      </div>
    </section>
  );
}

function CheckRow({ icon: Icon, title, state, children }: { icon: LucideIcon; title: string; state: RowState; children: ReactNode }) {
  const StateIcon = ROW_ICONS[state];
  return (
    <div className={`check-row check-${state}`}>
      <div className="check-head">
        <Icon size={20} aria-hidden />
        <h2>{title}</h2>
        <StateIcon size={20} className={`check-state${state === "checking" ? " spin" : ""}`} aria-label={STATE_NAMES[state]} />
      </div>
      <div className="check-body">{children}</div>
    </div>
  );
}

const STATE_NAMES: Record<RowState, string> = { open: "Offen", checking: "Wird geprüft", passed: "Bestanden", problem: "Problem" };
