// The live chat's status logic: the note-taker's tool calls from the data channel (when they start,
// when they end, where their tag sits), the status order, and the start of the follow-up round.
import { describe, expect, it } from "vitest";
import { displayStatus, reduceToolCalls, startsFollowUpRound, type ChannelEvent, type ToolCall } from "./status";

const functionCall = (name: string, callId = "call_1", type = "response.output_item.done", delegationId = "delegation_1"): ChannelEvent => ({
  type: "response.event",
  delegation_id: delegationId,
  event: { type, item: { type: "function_call", name, call_id: callId } },
});

const responseCreated = (delegationId = "delegation_1"): ChannelEvent => ({
  type: "response.event",
  delegation_id: delegationId,
  event: { type: "response.created" },
});

const sessionUpdated = (tools: string[]): ChannelEvent => ({
  type: "session.updated",
  session: { delegation: { responses: { tools: tools.map((name) => ({ name })) } } },
});

describe("reduceToolCalls", () => {
  it("adds a call once, as soon as the note-taker begins it, at the number of messages so far", () => {
    const begun = reduceToolCalls([], functionCall("submit_initial", "call_1", "response.output_item.added"), 7);
    expect(begun).toEqual([{ callId: "call_1", tool: "submit_initial", delegationId: "delegation_1", running: true, at: 7 }]);

    // Its `done` event (or a replay) adds nothing new and keeps the first position.
    expect(reduceToolCalls(begun, functionCall("submit_initial"), 9)).toBe(begun);

    // A call missed at `added` is added at `done`.
    expect(reduceToolCalls([], functionCall("web_search", "call_2"), 3)[0]).toMatchObject({ tool: "web_search", at: 3 });
  });

  it("ends with the next response of its delegation and ignores other delegations", () => {
    const calls = reduceToolCalls([], functionCall("web_search"), 2);

    expect(reduceToolCalls(calls, responseCreated("delegation_2"), 2)).toBe(calls);
    expect(reduceToolCalls(calls, responseCreated(), 2)).toEqual([{ ...calls[0], running: false }]);
  });

  it("ignores unknown tools and every other event", () => {
    const calls: ToolCall[] = [];

    expect(reduceToolCalls(calls, functionCall("toString"), 0)).toBe(calls);
    expect(reduceToolCalls(calls, { type: "session.output_transcript.delta", delta: "Moment." }, 0)).toBe(calls);
    expect(reduceToolCalls(calls, { type: "response.event", delegation_id: "delegation_1" }, 0)).toBe(calls);
  });
});

describe("displayStatus", () => {
  it("shows the latest running tool, then speaking, then muted, then listening", () => {
    const searching = reduceToolCalls([], functionCall("web_search", "call_1"), 0);
    const writing = reduceToolCalls(searching, functionCall("submit_initial", "call_2"), 4);
    const done = reduceToolCalls(writing, responseCreated(), 4);

    expect(displayStatus(writing, true, true)).toBe("submit_initial");
    expect(displayStatus(done, true, true)).toBe("speaking");
    expect(displayStatus(done, false, true)).toBe("muted");
    expect(displayStatus(done, false, false)).toBe("listening");
  });
});

describe("startsFollowUpRound", () => {
  it("is true only for a session.updated that brings submit_follow_up", () => {
    expect(startsFollowUpRound(sessionUpdated(["web_search", "submit_follow_up"]))).toBe(true);
    expect(startsFollowUpRound(sessionUpdated(["web_search", "submit_initial"]))).toBe(false);
    expect(startsFollowUpRound({ type: "session.updated" })).toBe(false);
    expect(startsFollowUpRound({ ...sessionUpdated(["submit_follow_up"]), type: "session.started" })).toBe(false);
  });
});
