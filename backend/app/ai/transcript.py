"""Transcript messages and reply times from the Live API's transcript deltas.

The Live API sends the founder's and the agent's words as deltas (`session.input_transcript.delta`
and `session.output_transcript.delta`), each with `start_ms` and `end_ms` from the session start,
but no turn IDs. So a message is defined by one rule, written down at `schemas.TranscriptMessage`,
which a live transcript in the browser must follow as well: a speaker change starts a new message.

A reply time is the time from the end of the founder's words to the start of the agent's answer:
`agent.start_ms - founder.end_ms` at every switch from founder to agent. Negative values are
overlaps, such as a founder's "mhm" while the agent speaks, and are not counted.

Pure in-memory logic; it runs on the event loop inside the call's sideband task and never waits.
"""

import statistics

from app.schemas import Speaker, TranscriptMessage


class TranscriptBuilder:
    """Collects the deltas of the current message and hands out each message once it is finished."""

    def __init__(self) -> None:
        self.speaker: Speaker | None = None  # who spoke last; the goodbye watch reads it
        self._parts: list[str] = []
        self._start_ms = 0
        self._end_ms = 0

    def add(self, speaker: Speaker, delta: str, start_ms: int, end_ms: int) -> TranscriptMessage | None:
        """Adds a delta; returns the previous speaker's message when this delta starts a new one."""
        finished = None
        if speaker != self.speaker:
            finished = self.flush()
            self.speaker = speaker
            self._start_ms = start_ms
        self._parts.append(delta)
        self._end_ms = end_ms
        return finished

    def flush(self) -> TranscriptMessage | None:
        """The message in progress, finished now (at a speaker change or at the end); None if empty."""
        if self.speaker is None:
            return None
        message_text = "".join(self._parts).strip()
        self._parts = []
        if not message_text:
            return None
        return TranscriptMessage(speaker=self.speaker, text=message_text, start_ms=self._start_ms, end_ms=self._end_ms)


class ReplyTimes:
    """The reply times of one conversation, for its log lines."""

    def __init__(self) -> None:
        self.values: list[int] = []

    def record(self, founder_end_ms: int, agent_start_ms: int) -> int | None:
        """The reply time of one switch from founder to agent; None (not counted) for an overlap."""
        reply_ms = agent_start_ms - founder_end_ms
        if reply_ms < 0:
            return None
        self.values.append(reply_ms)
        return reply_ms

    def summary(self) -> tuple[int, int, int]:
        """Count, median and maximum in ms (zeros without any reply)."""
        if not self.values:
            return 0, 0, 0
        return len(self.values), round(statistics.median(self.values)), max(self.values)
