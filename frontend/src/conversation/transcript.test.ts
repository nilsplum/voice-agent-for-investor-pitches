// The live transcript follows the backend's message rule (backend/app/ai/transcript.py and its tests).
import { describe, expect, it } from "vitest";
import type { Speaker, TranscriptMessage } from "../api/client";
import { appendDelta, finishLast } from "./transcript";

function build(deltas: [Speaker, string][]): TranscriptMessage[] {
  return deltas.reduce<TranscriptMessage[]>(
    (messages, [speaker, delta], index) => appendDelta(messages, speaker, delta, index * 100, index * 100 + 50),
    [],
  );
}

describe("appendDelta", () => {
  it("joins the deltas of one speaker as received and starts a new message when the speaker changes", () => {
    const messages = build([["agent", "Guten "], ["agent", "Tag."], ["founder", "Hallo"]]);

    expect(messages).toEqual([
      { speaker: "agent", text: "Guten Tag.", start_ms: 0, end_ms: 150 },
      { speaker: "founder", text: "Hallo", start_ms: 200, end_ms: 250 },
    ]);
  });

  it("trims a message once it is finished, and only then", () => {
    const messages = build([["agent", " Guten Tag. "], ["founder", " Hallo "]]);

    expect(messages.map((message) => message.text)).toEqual(["Guten Tag.", " Hallo "]);
    expect(finishLast(messages).map((message) => message.text)).toEqual(["Guten Tag.", "Hallo"]);
  });

  it("drops an empty message, and the next one starts anew instead of continuing the one before", () => {
    const messages = build([["agent", "Erste Frage."], ["founder", "  "], ["agent", "Zweite Frage."]]);

    expect(messages.map((message) => [message.speaker, message.text])).toEqual([
      ["agent", "Erste Frage."],
      ["agent", "Zweite Frage."],
    ]);
  });

  it("finishes nothing when there is no message yet", () => {
    expect(finishLast([])).toEqual([]);
  });
});
