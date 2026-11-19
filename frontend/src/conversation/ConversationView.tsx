/**
 * The one conversation view: the transcript in chat style (the founder on the right, the agent on
 * the left), the status of a running call, an action slot (STOPP during a call, „Aktualisieren" for
 * a conversation running elsewhere) and the outcome message below the messages.
 *
 * Used for the founder's running call (filled live from the data channel, call/useCall.ts), for a
 * founder's past conversations and for the Team area (both filled from the database). It shows only
 * what was said and, live, that a tool runs: each of the note-taker's tool calls is a small tag
 * between the messages, and the follow-up round sits in its own „Rückfragen" section. Founders see
 * only that a tool runs, never what it does: never the note-taker's work, the questionnaire or the
 * reviewer's text. The tags and the section exist only live (they are not stored), so a stored
 * conversation shows the messages alone.
 *
 * It renders its three parts (the bar, the messages and the outcome) into the card its page gives
 * it: on the founder's page a fill card, so the bar and the outcome always stay in view and only the
 * messages scroll; in the Team area a card whose messages pane is capped in height (the scroll
 * model in styles/base.css). The messages pane scrolls, never the window: it follows new text only
 * while the reader is at its bottom, so someone who scrolled up to reread stays where they are, and
 * a stored conversation opens at its beginning.
 */
import { Check, LoaderCircle } from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import type { ConversationView as StoredConversation, TranscriptMessage } from "../api/client";
import { TOOL_LABELS } from "../labels";
import { OutcomeMessage } from "./OutcomeMessage";
import type { CallStatus, FollowUpStart, ToolCall } from "./status";
import { StatusPill } from "./StatusPill";

// How close to the bottom (about 3rem) counts as reading the newest message.
const FOLLOW_DISTANCE_PX = 48;
const NO_TOOL_CALLS: ToolCall[] = []; // one array, so the auto-scroll does not rerun on every render

type Props = {
  messages: TranscriptMessage[];
  agentName: string | null;
  founderLabel: string; // „Sie" for the founder, the founder's name in the Team area
  status?: CallStatus; // only during a call
  toolCalls?: ToolCall[]; // only during a call: the note-taker's tool calls, shown as tags
  followUpFrom?: FollowUpStart | null; // only during a call: where the „Rückfragen" section starts
  outcome?: StoredConversation; // the stored conversation whose outcome is shown below the messages
  actions?: ReactNode;
};

// One entry of the chat: a message (with its index in the full list) or a tool call's tag.
type Entry = { message: TranscriptMessage; index: number } | { call: ToolCall; order: number };

function atBottom(pane: HTMLElement): boolean {
  return pane.scrollHeight - pane.scrollTop - pane.clientHeight <= FOLLOW_DISTANCE_PX;
}

/** The messages and the tags in their order: each tag right after the message that was last when its
 * tool call started. A message still without words is left out; its tags keep their place. */
function entries(messages: TranscriptMessage[], toolCalls: ToolCall[]): Entry[] {
  const chat: Entry[] = [];
  const tags = toolCalls.map((call, order) => ({ call, order }));
  messages.forEach((message, index) => {
    chat.push(...tags.filter(({ call }) => call.at === index));
    if (message.text.trim()) chat.push({ message, index });
  });
  chat.push(...tags.filter(({ call }) => call.at >= messages.length));
  return chat;
}

function inFollowUpRound(entry: Entry, start: FollowUpStart): boolean {
  return "message" in entry ? entry.index >= start.messages : entry.order >= start.toolCalls;
}

export function ConversationView(props: Props) {
  const { messages, agentName, founderLabel, status, toolCalls = NO_TOOL_CALLS, followUpFrom = null, outcome, actions } = props;
  const chat = entries(messages, toolCalls);
  const live = status !== undefined;
  const pane = useRef<HTMLDivElement>(null);
  // Whether the reader is at the newest message, measured on every scroll and after every change. A
  // live call starts there; a stored conversation opens at its beginning.
  const following = useRef(live);

  // Before the browser paints new text, a new tag or the outcome (which takes height from the pane):
  // scroll to the bottom if the reader was there, then measure again for the next change. A hidden
  // pane (the Team area's closed „Gesprächsverlauf") has no size to measure and is left alone.
  useLayoutEffect(() => {
    const element = pane.current;
    if (!element?.checkVisibility()) return;
    if (following.current) element.scrollTop = element.scrollHeight;
    following.current = atBottom(element);
  }, [messages, toolCalls, followUpFrom, outcome?.state]);

  function show(entry: Entry): ReactNode {
    if ("call" in entry) {
      const { call } = entry;
      const label = TOOL_LABELS[call.tool];
      // A tag, not a bubble: the voice test reads only the .bubble elements as messages.
      return (
        <li key={call.callId} className={`tool-tag tone-${label.tone}`}>
          {call.running ? <LoaderCircle size={14} className="spin" aria-hidden /> : <Check size={14} aria-hidden />}
          {call.running ? label.running : label.done}
        </li>
      );
    }
    const { message, index } = entry;
    return (
      <li key={`${message.speaker}-${message.start_ms}-${index}`} className={`bubble bubble-${message.speaker}`}>
        <span className="bubble-speaker">{message.speaker === "founder" ? founderLabel : agentName ?? "Agent"}</span>
        <p>{message.text.trim()}</p>
      </li>
    );
  }

  const before = followUpFrom ? chat.filter((entry) => !inFollowUpRound(entry, followUpFrom)) : chat;
  const round = followUpFrom ? chat.filter((entry) => inFollowUpRound(entry, followUpFrom)) : [];
  return (
    <>
      {(status || actions) && (
        <div className="conversation-bar">
          {status && <StatusPill status={status} />}
          <div className="conversation-actions">{actions}</div>
        </div>
      )}
      <div
        ref={pane}
        className="scroll-pane conversation-messages"
        onScroll={() => {
          if (pane.current) following.current = atBottom(pane.current);
        }}
      >
        {chat.length === 0 && !live && <p className="muted">Noch keine Nachrichten.</p>}
        {chat.length > 0 && (
          <ol className="transcript">
            {before.map(show)}
            {followUpFrom && (
              <li className="follow-up-section">
                <div className="section-divider"><span className="label-pill">Rückfragen</span></div>
                <ol className="transcript">{round.map(show)}</ol>
              </li>
            )}
          </ol>
        )}
      </div>
      {outcome && <OutcomeMessage view={outcome} />}
    </>
  );
}
