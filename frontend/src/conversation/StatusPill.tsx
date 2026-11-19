/**
 * The status of a running call (conversation/status.ts) as a pill in the conversation's bar. While a
 * tool runs, it shows the tool's running label in the tool's tone (labels.ts, the same colours as
 * its tag in the chat); otherwise the call's own state, „Mikrofon stumm" in the warning colours.
 * Screen readers announce its changes. The voice test reads its text („Hört zu", „Schreibt Ihre
 * Antworten auf ...").
 */
import { AudioLines, Ear, LoaderCircle, MicOff, PenLine, Search, type LucideIcon } from "lucide-react";
import { TOOL_LABELS, type ToolTone } from "../labels";
import { isTool, STATUS_LABELS, type CallState, type CallStatus } from "./status";

const STATE_ICONS: Record<CallState, LucideIcon> = {
  connecting: LoaderCircle,
  listening: Ear,
  speaking: AudioLines,
  muted: MicOff,
  ending: LoaderCircle,
};

const TONE_ICONS: Record<ToolTone, LucideIcon> = {
  search: Search,
  writing: PenLine,
};

export function StatusPill({ status }: { status: CallStatus }) {
  const shown = isTool(status)
    ? { Icon: TONE_ICONS[TOOL_LABELS[status].tone], label: TOOL_LABELS[status].running, colour: `tone-${TOOL_LABELS[status].tone}` }
    : { Icon: STATE_ICONS[status], label: STATUS_LABELS[status], colour: `status-${status}` };
  const busy = status === "connecting" || status === "ending";
  return (
    <span className={`status-pill ${shown.colour}`} role="status" aria-live="polite">
      <shown.Icon size={16} aria-hidden className={busy ? "spin" : undefined} />
      {shown.label}
    </span>
  );
}
