/**
 * The audio level of a MediaStream, measured one way for the whole app: a Web Audio AnalyserNode
 * and the RMS of its samples (0 to 1), once per animation frame. Two hooks share this measurement:
 * - `useAudioLevel`: the level itself, for the device check's microphone meter (a new value every
 *   frame).
 * - `useSpeaking`: whether the agent speaks, for the call's „Spricht"; the Live API has no events
 *   for speech starting or stopping. It holds „speaking" for a while after the level dropped, so the
 *   status does not flicker between words, and it changes state only when that answer flips, so the
 *   conversation view does not re-render every frame.
 *
 * Each measurement opens its own AudioContext and closes it when the stream changes or the
 * component unmounts. The contexts are created after a click (the device check, START), so the
 * browser lets them run. Chrome delivers a remote WebRTC stream to Web Audio only while it also
 * plays in a media element, which the call does (audio/speaker.ts).
 */
import { useEffect, useState } from "react";

function watchLevel(stream: MediaStream, onLevel: (level: number) => void): () => void {
  const context = new AudioContext();
  void context.resume();
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  context.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  let frame = requestAnimationFrame(function measure() {
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (const sample of samples) sum += sample * sample;
    onLevel(Math.sqrt(sum / samples.length));
    frame = requestAnimationFrame(measure);
  });
  return () => {
    cancelAnimationFrame(frame);
    void context.close();
  };
}

/** The stream's current level (0 to 1); 0 without a stream. */
export function useAudioLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!stream) return;
    const stop = watchLevel(stream, setLevel);
    return () => {
      stop();
      setLevel(0);
    };
  }, [stream]);
  return level;
}

/** Whether the stream's level was above `threshold` within the last `holdMs`. */
export function useSpeaking(stream: MediaStream | null, threshold: number, holdMs: number): boolean {
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => {
    if (!stream) return;
    let lastLoud = -Infinity;
    const stop = watchLevel(stream, (level) => {
      const now = performance.now();
      if (level > threshold) lastLoud = now;
      setSpeaking(now - lastLoud < holdMs); // React skips the render when the answer is unchanged
    });
    return () => {
      stop();
      setSpeaking(false);
    };
  }, [stream, threshold, holdMs]);
  return speaking;
}
