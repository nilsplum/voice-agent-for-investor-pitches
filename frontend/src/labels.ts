/**
 * The German labels of the backend's enum values, written once. Each record is typed with the
 * generated types, so a new value in the backend fails the type check until it has a label here.
 */
import type { AccessCodeRow, ConversationState, EndReason, Me, ToolName } from "./api/client";

export const ROLE_AREAS: Record<Me["role"], string> = {
  founder: "Gründerbereich",
  team: "Teambereich",
};

export const CONVERSATION_STATE_LABELS: Record<ConversationState, string> = {
  ready: "Bereit",
  in_progress: "Läuft",
  completed: "Abgeschlossen",
  unfinished: "Nicht abgeschlossen",
};

export const ACCESS_CODE_STATE_LABELS: Record<AccessCodeRow["state"], string> = {
  unused: "Unbenutzt",
  used: "Benutzt",
  expired: "Abgelaufen",
};

// Why an Unfinished conversation ended, as the outcome message says it. Neutral wording, because the
// team sees the same message.
export const END_REASON_TEXTS: Record<EndReason, string> = {
  stopped: "Das Gespräch wurde mit STOPP beendet.",
  connection_lost: "Die Verbindung wurde unterbrochen.",
  time_limit: "Das Zeitlimit wurde erreicht.",
};

// The colour of a tool in the status pill and in its tag in the live chat (the tone-* classes of
// styles/base.css, built on the existing colour tokens).
export type ToolTone = "search" | "writing";

// The note-taker's tools as founders see them: the status pill while one runs, and its tag in the
// live chat (running, then done). Founders see only that a tool runs, never what it does. „Schreibt
// Ihre Antworten auf ..." stays word for word: the voice test waits for it.
export const TOOL_LABELS: Record<ToolName, { running: string; done: string; tone: ToolTone }> = {
  web_search: { running: "Sucht im Internet ...", done: "Im Internet gesucht", tone: "search" },
  submit_initial: { running: "Schreibt Ihre Antworten auf ...", done: "Antworten aufgeschrieben", tone: "writing" },
  submit_follow_up: { running: "Schreibt Ihre Antworten auf ...", done: "Rückfragen aufgeschrieben", tone: "writing" },
};
