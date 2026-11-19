/**
 * Sound out of the speaker the founder chose in the device check. The test tone and the agent's
 * voice take the same path, an <audio> element playing a MediaStream on the chosen output, so a test
 * tone the founder heard means the agent will be heard too.
 *
 * Choosing the output needs `setSinkId`, which Chrome and Edge offer and not every other browser;
 * elsewhere the sound plays on the default speaker (the device check says so).
 */

export const CAN_CHOOSE_SPEAKER = typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;

/** An audio element that plays whatever stream it is given on the chosen speaker ("" = default). */
export function openSpeaker(speakerId: string): HTMLAudioElement {
  const audio = new Audio();
  audio.autoplay = true;
  if (CAN_CHOOSE_SPEAKER && speakerId) {
    // A speaker that disappeared meanwhile leaves the default one, which is still better than silence.
    audio.setSinkId(speakerId).catch(() => undefined);
  }
  return audio;
}

const TEST_TONE = [
  { frequency: 660, startS: 0 },
  { frequency: 880, startS: 0.22 },
];
const TONE_LENGTH_S = 0.35;

/** The device check's test tone: a short two-tone chime, generated with Web Audio. */
export function playTestTone(speakerId: string): void {
  const context = new AudioContext();
  const output = context.createMediaStreamDestination();
  for (const { frequency, startS } of TEST_TONE) {
    const start = context.currentTime + startS;
    const oscillator = context.createOscillator();
    const volume = context.createGain();
    oscillator.frequency.value = frequency;
    // A soft attack and a fade-out, so the tone neither clicks nor cuts off.
    volume.gain.setValueAtTime(0, start);
    volume.gain.linearRampToValueAtTime(0.3, start + 0.02);
    volume.gain.exponentialRampToValueAtTime(0.001, start + TONE_LENGTH_S);
    oscillator.connect(volume).connect(output);
    oscillator.start(start);
    oscillator.stop(start + TONE_LENGTH_S);
  }
  const audio = openSpeaker(speakerId);
  audio.srcObject = output.stream;
  setTimeout(() => {
    audio.srcObject = null;
    void context.close();
  }, 1000);
}
