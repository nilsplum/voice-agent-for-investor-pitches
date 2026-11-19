/**
 * What the founder sees of a running call besides the words: the status pill, the tool tags in the
 * live chat, and where the follow-up round starts. It comes from three places:
 * - The note-taker's tool calls, from its events on the data channel. OpenAI forwards the
 *   note-taker's Responses events to the browser wrapped in `response.event`, each with its
 *   `delegation_id`. A function call is known as soon as the note-taker begins it (nested
 *   `response.output_item.added`), so „Schreibt Ihre Antworten auf ..." already shows while the
 *   note-taker composes the answers; its `response.output_item.done` adds it too, in case the first
 *   was missed. The next nested `response.created` of the same delegation marks it as done, because
 *   the note-taker's next response only starts once the backend sent the tool's output. Each call
 *   keeps its position in the chat: the number of messages when it started.
 * - Whether the agent speaks, measured from its audio (audio/useAudioLevel.ts), because the Live
 *   API has no events for speech starting or stopping; and whether the founder muted the microphone
 *   (the header's mute button), so a founder who talks and gets no answer sees why.
 * - The switch to the follow-up tools: the backend's `session.update` comes back on the data
 *   channel as `session.updated`, whose delegation tools then include `submit_follow_up`.
 * The status is the latest running tool, then speaking, then muted, then listening. The labels and
 * colours of the tools live in labels.ts (TOOL_LABELS). Pure functions, unit tested in
 * status.test.ts.
 */
import type { ToolName } from "../api/client";
import { TOOL_LABELS } from "../labels";

/** The call's own states; while a tool runs, the status is the tool's name instead. */
export type CallState = "connecting" | "listening" | "speaking" | "muted" | "ending";
export type CallStatus = CallState | ToolName;

export const STATUS_LABELS: Record<CallState, string> = {
  connecting: "Verbinde ...",
  listening: "Hört zu",
  speaking: "Spricht",
  muted: "Mikrofon stumm",
  ending: "Wird beendet ...",
};

/** One tool call of the note-taker, as the browser follows it. */
export type ToolCall = {
  callId: string;
  tool: ToolName;
  delegationId: string | null;
  running: boolean;
  at: number; // the number of messages when it started: its tag sits right after the last of them
};

/** Where the follow-up round starts in the live chat: the number of messages and of tool calls at the
 * switch. Everything after them sits in the „Rückfragen" section; the tool call that was running
 * at the switch (writing down the answers) stays before it. */
export type FollowUpStart = { messages: number; toolCalls: number };

/** The few fields of OpenAI's data channel events that the browser reads. */
export type ChannelEvent = {
  type?: string;
  delta?: string;
  start_ms?: number;
  end_ms?: number;
  delegation_id?: string | null;
  event?: { type?: string; item?: { type?: string; name?: string; call_id?: string; id?: string } };
  session?: { delegation?: { responses?: { tools?: { name?: string }[] } } }; // in session.updated
};

export function isTool(name: string): name is ToolName {
  return Object.hasOwn(TOOL_LABELS, name);
}

export function reduceToolCalls(calls: ToolCall[], event: ChannelEvent, messageCount: number): ToolCall[] {
  const nested = event.type === "response.event" ? event.event : undefined;
  if (!nested) return calls;
  const delegationId = event.delegation_id ?? null;
  const item = nested.item;
  if (item?.type === "function_call" && (nested.type === "response.output_item.added" || nested.type === "response.output_item.done")) {
    const callId = item.call_id ?? item.id;
    const name = item.name ?? "";
    if (!callId || !isTool(name) || calls.some((call) => call.callId === callId)) return calls;
    return [...calls, { callId, tool: name, delegationId, running: true, at: messageCount }];
  }
  if (nested.type === "response.created" && calls.some((call) => call.running && call.delegationId === delegationId)) {
    return calls.map((call) => (call.running && call.delegationId === delegationId ? { ...call, running: false } : call));
  }
  return calls;
}

export function displayStatus(calls: ToolCall[], agentSpeaking: boolean, muted: boolean): CallStatus {
  const running = calls.findLast((call) => call.running);
  return running?.tool ?? (agentSpeaking ? "speaking" : muted ? "muted" : "listening");
}

/** True for the `session.updated` that brings the follow-up round's tools. */
export function startsFollowUpRound(event: ChannelEvent): boolean {
  return event.type === "session.updated"
    && (event.session?.delegation?.responses?.tools ?? []).some((tool) => tool.name === "submit_follow_up");
}
