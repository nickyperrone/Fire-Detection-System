"use client";

import { useSyncExternalStore } from "react";

// Actions that failed with nothing on the page to say so: each one bumps this count, and the
// toast shows one friendly line. Never the server's own words (docs/04-frontend.md#errors).
let failures = 0;
const listeners = new Set<() => void>();

export function reportFailure(): void {
  failures += 1;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useFailures(): number {
  return useSyncExternalStore(
    subscribe,
    () => failures,
    () => 0,
  );
}
