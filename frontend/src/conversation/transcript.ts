/**
 * The live transcript of a running call, built in the browser from the transcript deltas on the
 * data channel. It follows the backend's rule exactly (the one definition is the description of
 * TranscriptMessage in backend/app/schemas.py, built there by app/ai/transcript.py): a speaker
 * change starts a new message; a message's text is its deltas joined as received, trimmed once it
 * is finished; an empty message is dropped. The last message is the one in progress.
 *
 * When the call ends, the page shows the backend's stored transcript instead, which the same rule
 * built from the same deltas. Pure functions, unit tested in transcript.test.ts.
 */
import type { Speaker, TranscriptMessage } from "../api/client";

// The data channel events that carry the transcript, and whose words they are.
export const TRANSCRIPT_EVENTS: Partial<Record<string, Speaker>> = {
  "session.input_transcript.delta": "founder",
  "session.output_transcript.delta": "agent",
};

export function appendDelta(
  messages: TranscriptMessage[],
  speaker: Speaker,
  delta: string,
  startMs: number,
  endMs: number,
): TranscriptMessage[] {
  const last = messages.at(-1);
  if (last?.speaker === speaker) {
    return [...messages.slice(0, -1), { ...last, text: last.text + delta, end_ms: endMs }];
  }
  return [...finishLast(messages), { speaker, text: delta, start_ms: startMs, end_ms: endMs }];
}

/** Finishes the message in progress: trimmed, or dropped if nothing was said. */
export function finishLast(messages: TranscriptMessage[]): TranscriptMessage[] {
  const last = messages.at(-1);
  if (!last) return messages;
  const text = last.text.trim();
  return text ? [...messages.slice(0, -1), { ...last, text }] : messages.slice(0, -1);
}
