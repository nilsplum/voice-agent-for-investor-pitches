/**
 * The founder's call: the browser side of the conversation (README, Architecture). The audio goes
 * straight between the browser and OpenAI over WebRTC; the backend creates the Live session, so the
 * OpenAI key never reaches the browser, and runs the tools through its sideband.
 *
 * - START: a peer connection with the page's microphone track and the data channel `oai-events`
 *   (created before the offer, so it is part of it). The offer is sent once it lists all of the
 *   browser's network addresses, because OpenAI takes no later ones. The backend creates the
 *   session with it and returns OpenAI's answer. If that request fails, no call exists and the
 *   error goes to the page.
 * - While the call runs: the agent's voice plays on the chosen speaker (audio/speaker.ts); the data
 *   channel's events feed the live chat: the transcript (conversation/transcript.ts), the
 *   note-taker's tool calls, shown as the status and as tags, and the start of the follow-up round
 *   (conversation/status.ts); „Spricht" comes from the agent's audio level. The tags and the round's
 *   section exist only live: after the call, the page shows the stored conversation.
 * - Every end runs `handleEnd` exactly once: STOPP, the session closing (after the goodbye, or ended
 *   by the backend), a broken connection, leaving the page or closing the tab. It mutes the agent at
 *   once, reports the end and waits for the stored conversation, and only then closes the
 *   connection: closing first would make OpenAI end the session as lost before the backend recorded
 *   STOPP. The report is sent with `keepalive`, so it reaches the backend while a tab is closing.
 * - The microphone belongs to the page, never to the call, so a retry after a failed start uses the
 *   same stream and asks for no permission again. The call keeps it only to mute it: the header's
 *   mute button (`muted` in the AppProvider) disables the tracks the call sends, so OpenAI hears
 *   only silence while the session and the connection stay as they are, and unmuting works at once.
 *   Every end enables the tracks again and resets `muted`, so a retry starts with a live microphone.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ConversationView,
  type EndRequest,
  type StartResponse,
  type TranscriptMessage,
} from "../api/client";
import { useApp } from "../AppProvider";
import { openSpeaker } from "../audio/speaker";
import { useSpeaking } from "../audio/useAudioLevel";
import {
  displayStatus,
  reduceToolCalls,
  startsFollowUpRound,
  type CallStatus,
  type ChannelEvent,
  type FollowUpStart,
  type ToolCall,
} from "../conversation/status";
import { appendDelta, TRANSCRIPT_EVENTS } from "../conversation/transcript";

// idle: no call. starting: the START request runs. connecting: the call exists, the data channel is
// not open yet. live: the call runs. ending: handleEnd runs.
export type CallPhase = "idle" | "starting" | "connecting" | "live" | "ending";

type Connection = {
  conversationId: string;
  microphone: MediaStream; // the page's stream; the call only mutes and unmutes its tracks
  peer: RTCPeerConnection;
  speaker: HTMLAudioElement;
  answered: Promise<boolean>; // whether the START request created a call at the backend
  ending: boolean;
};

/** Waits until the offer lists all of the browser's network addresses, at most `timeoutMs`. */
function gatheringComplete(peer: RTCPeerConnection, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => {
      if (peer.iceGatheringState === "complete") done();
    };
    const timer = setTimeout(done, timeoutMs);
    peer.addEventListener("icegatheringstatechange", check);
    check();
  });
}

/** Enables or disables the microphone tracks the call sends; a disabled track sends silence. */
function setMicrophone(microphone: MediaStream, on: boolean): void {
  for (const track of microphone.getAudioTracks()) track.enabled = on;
}

function parse(data: unknown): ChannelEvent | null {
  try {
    const event: unknown = JSON.parse(String(data));
    return typeof event === "object" && event !== null ? (event as ChannelEvent) : null;
  } catch {
    return null; // not an event; the data channel carries only JSON
  }
}

/** What the live chat shows besides the status, built from the data channel's events. */
type LiveChat = { messages: TranscriptMessage[]; toolCalls: ToolCall[]; followUpFrom: FollowUpStart | null };

const EMPTY_CHAT: LiveChat = { messages: [], toolCalls: [], followUpFrom: null };

function reduceChat(chat: LiveChat, event: ChannelEvent): LiveChat {
  const speaker = TRANSCRIPT_EVENTS[event.type ?? ""];
  if (speaker) {
    return { ...chat, messages: appendDelta(chat.messages, speaker, event.delta ?? "", event.start_ms ?? 0, event.end_ms ?? 0) };
  }
  const toolCalls = reduceToolCalls(chat.toolCalls, event, chat.messages.length);
  const followUpFrom = chat.followUpFrom
    ?? (startsFollowUpRound(event) ? { messages: chat.messages.length, toolCalls: chat.toolCalls.length } : null);
  return toolCalls === chat.toolCalls && followUpFrom === chat.followUpFrom ? chat : { ...chat, toolCalls, followUpFrom };
}

/** `onEnded` gets the stored conversation the end report returned, or null if the report failed. */
export function useCall(onEnded: (view: ConversationView | null) => void) {
  const { appConfig, setCallActive, muted, setMuted } = useApp();
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [chat, setChat] = useState<LiveChat>(EMPTY_CHAT);
  const [agentName, setAgentName] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null); // when START was pressed, for the page's date
  const [agentAudio, setAgentAudio] = useState<MediaStream | null>(null);
  const speaking = useSpeaking(agentAudio, appConfig.speaking_level_threshold, appConfig.speaking_hold_ms);
  const connection = useRef<Connection | null>(null);
  const ended = useRef(onEnded);
  useEffect(() => {
    ended.current = onEnded;
  });

  const handleEnd = useCallback(async (reason: EndRequest["reason"]) => {
    const current = connection.current;
    if (!current || current.ending) return;
    current.ending = true;
    current.speaker.muted = true;
    setPhase("ending");
    // An end while START still runs (the page was left) waits for it: a failed START left no call
    // to report, and start() cleans up after itself.
    if (!(await current.answered)) return;
    let view: ConversationView | null = null;
    try {
      view = await api.endConversation(current.conversationId, reason);
    } catch {
      // The page loads the conversation itself.
    }
    current.peer.close();
    current.speaker.srcObject = null;
    setMicrophone(current.microphone, true);
    connection.current = null;
    setAgentAudio(null);
    setPhase("idle");
    ended.current(view);
  }, []);

  const start = useCallback(
    async (conversationId: string, microphone: MediaStream, speakerId: string) => {
      const peer = new RTCPeerConnection();
      const speaker = openSpeaker(speakerId);
      let answered: (created: boolean) => void = () => undefined;
      const current: Connection = {
        conversationId,
        microphone,
        peer,
        speaker,
        answered: new Promise((resolve) => (answered = resolve)),
        ending: false,
      };
      connection.current = current;
      setChat(EMPTY_CHAT);
      setAgentName(null);
      setStartedAt(new Date().toISOString());
      setPhase("starting");

      peer.ontrack = (event) => {
        const stream = event.streams[0] ?? new MediaStream([event.track]);
        speaker.srcObject = stream;
        setAgentAudio(stream);
      };
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === "failed" || peer.connectionState === "closed") void handleEnd("connection_lost");
      };
      for (const track of microphone.getAudioTracks()) peer.addTrack(track, microphone);
      const channel = peer.createDataChannel("oai-events");
      channel.onopen = () => {
        if (!current.ending) setPhase("live");
      };
      channel.onclose = () => void handleEnd("connection_lost");
      channel.onmessage = (message) => {
        const event = parse(message.data);
        if (!event) return;
        if (event.type === "session.closed") void handleEnd("connection_lost");
        else setChat((now) => reduceChat(now, event));
      };

      let answer: StartResponse;
      try {
        await peer.setLocalDescription(await peer.createOffer());
        await gatheringComplete(peer, appConfig.ice_gathering_timeout_ms);
        answer = await api.startConversation(conversationId, peer.localDescription?.sdp ?? "");
      } catch (failure) {
        // No call exists at the backend, so there is nothing to report.
        answered(false);
        if (connection.current === current) connection.current = null;
        setMicrophone(microphone, true);
        peer.close();
        setPhase("idle");
        throw failure;
      }
      answered(true);
      if (current.ending) return; // the page was left meanwhile; handleEnd reports and closes
      setAgentName(answer.agent_name);
      setPhase("connecting");
      try {
        await peer.setRemoteDescription({ type: "answer", sdp: answer.sdp });
      } catch {
        void handleEnd("connection_lost");
      }
    },
    [appConfig.ice_gathering_timeout_ms, handleEnd],
  );

  // While a call runs: the header hides its links and offers the mute button, and closing or
  // reloading the tab asks first. A tab that is closed anyway reports the end like a lost connection.
  const active = phase !== "idle";
  useEffect(() => {
    if (!active) return;
    setCallActive(true);
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    const leave = () => void handleEnd("connection_lost");
    window.addEventListener("beforeunload", warn);
    window.addEventListener("pagehide", leave);
    return () => {
      setCallActive(false);
      setMuted(false); // the tracks are enabled again where the call ended
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener("pagehide", leave);
    };
  }, [active, handleEnd, setCallActive, setMuted]);

  // The header's mute button: silence or restore the microphone of the running call.
  useEffect(() => {
    if (connection.current) setMicrophone(connection.current.microphone, !muted);
  }, [muted]);

  // No call outlives its page: leaving it inside the app (for example with Back) ends the call.
  useEffect(() => () => void handleEnd("connection_lost"), [handleEnd]);

  const stop = useCallback(() => void handleEnd("stopped"), [handleEnd]);
  const status: CallStatus =
    phase === "ending" ? "ending" : phase === "live" ? displayStatus(chat.toolCalls, speaking, muted) : "connecting";

  return {
    phase,
    messages: chat.messages,
    toolCalls: chat.toolCalls,
    followUpFrom: chat.followUpFrom,
    agentName,
    startedAt,
    status,
    canStop: phase === "connecting" || phase === "live", // STOPP once the call exists
    start,
    stop,
  };
}
