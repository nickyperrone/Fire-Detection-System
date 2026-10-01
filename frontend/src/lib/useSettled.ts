import { useEffect, useState } from "react";

/** `value` once it has stopped changing for `delayMs`; while a point is dragged it changes on
 * every frame, and only where it ends up is worth a request. */
export function useSettled<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}
