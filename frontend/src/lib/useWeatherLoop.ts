"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

// One frame every this long, and a longer look at the newest before starting over.
const STEP_MS = 650;
const HOLD_MS = 1800;
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeToMotion(onChange: () => void): () => void {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Which frame of the clouds and rain loop is on screen (docs/06-goes.md#clouds-and-rain-on-the-map).
 * It plays unless the system asks for less motion or the user pauses it; paused, the newest frame
 * shows.
 */
export function useWeatherLoop(count: number) {
  const reduced = useSyncExternalStore(
    subscribeToMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => true,
  );
  const [choice, setChoice] = useState<boolean | null>(null);
  const playing = (choice ?? !reduced) && count > 1;
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!playing) return;
    let timer = 0;
    const advance = (from: number) => {
      const next = (from + 1) % count;
      timer = window.setTimeout(
        () => {
          setStep(next);
          advance(next);
        },
        from === count - 1 ? HOLD_MS : STEP_MS,
      );
    };
    advance(0);
    return () => window.clearTimeout(timer);
  }, [playing, count]);

  return {
    shown: playing ? Math.min(step, count - 1) : count - 1,
    playing,
    toggle: () => setChoice(!playing),
  };
}
