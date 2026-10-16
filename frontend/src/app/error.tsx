"use client";

import { FriendlyError } from "@/components/FriendlyError";

/** Anything that breaks while the page draws: a plain sentence and a retry, never the stack
 * (docs/04-frontend.md#errors). */
export default function Error({
  reset,
}: {
  error: unknown;
  reset: () => void;
}) {
  return <FriendlyError onRetry={reset} />;
}
