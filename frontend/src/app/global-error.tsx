"use client";

import { FriendlyError } from "@/components/FriendlyError";

/** The same, when even the page's frame breaks. */
export default function GlobalError({
  reset,
}: {
  error: unknown;
  reset: () => void;
}) {
  return (
    <html lang="es">
      <body style={{ margin: 0, background: "#0b0e13" }}>
        <FriendlyError onRetry={reset} />
      </body>
    </html>
  );
}
