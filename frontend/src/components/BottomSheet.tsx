"use client";

import { useEffect, useRef, useState } from "react";

import { useLocale } from "@/i18n/LocaleProvider";

export type Snap = "peek" | "half" | "full";
const SNAPS: Snap[] = ["peek", "half", "full"];

export const PEEK_PX = 168;
const FRACTION: Record<Exclude<Snap, "peek">, number> = {
  half: 0.48,
  full: 0.9,
};

function heightFor(snap: Snap, viewport: number): number {
  return snap === "peek" ? PEEK_PX : viewport * FRACTION[snap];
}

function nearestSnap(height: number, viewport: number): Snap {
  return SNAPS.reduce((best, snap) =>
    Math.abs(heightFor(snap, viewport) - height) <
    Math.abs(heightFor(best, viewport) - height)
      ? snap
      : best,
  );
}

type Props = {
  snap: Snap;
  onSnapChange: (snap: Snap) => void;
  /** Changing it scrolls the content back to the top, e.g. when another field opens. */
  contentKey: string;
  /** Changing it scrolls back to the top without replaying the entrance, e.g. another tab. */
  scrollKey?: string;
  children: React.ReactNode;
};

/** Mobile: a sheet dragged between three heights. Desktop: a fixed panel on the left. */
export function BottomSheet({
  snap,
  onSnapChange,
  contentKey,
  scrollKey,
  children,
}: Props) {
  const { t } = useLocale();
  const [viewport, setViewport] = useState(800);
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const drag = useRef<{ startY: number; startHeight: number } | null>(null);
  const content = useRef<HTMLDivElement>(null);

  useEffect(() => {
    content.current?.scrollTo({ top: 0 });
  }, [contentKey, scrollKey]);

  useEffect(() => {
    const measure = () => setViewport(window.innerHeight);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const height = dragHeight ?? heightFor(snap, viewport);

  // Enter or Space cycles like a tap; the arrows step up and down.
  const onKeyDown = (e: React.KeyboardEvent) => {
    const at = SNAPS.indexOf(snap);
    const next =
      e.key === "Enter" || e.key === " "
        ? (at + 1) % SNAPS.length
        : e.key === "ArrowUp"
          ? Math.min(at + 1, SNAPS.length - 1)
          : e.key === "ArrowDown"
            ? Math.max(at - 1, 0)
            : null;
    if (next === null) return;
    e.preventDefault();
    onSnapChange(SNAPS[next]);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { startY: e.clientY, startHeight: height };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const next = drag.current.startHeight + (drag.current.startY - e.clientY);
    setDragHeight(Math.min(Math.max(next, PEEK_PX - 40), viewport * 0.94));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const moved = Math.abs(e.clientY - drag.current.startY);
    drag.current = null;
    setDragHeight(null);
    // A tap on the handle cycles up, like tapping the grabber in a maps app.
    if (moved < 6)
      onSnapChange(
        snap === "peek" ? "half" : snap === "half" ? "full" : "peek",
      );
    else onSnapChange(nearestSnap(height, viewport));
  };

  return (
    <section
      style={{ "--sheet-h": `${height}px` } as React.CSSProperties}
      className={`glass fixed inset-x-0 bottom-0 z-20 flex h-[var(--sheet-h)] flex-col rounded-t-3xl pb-[env(safe-area-inset-bottom)] ${
        dragHeight === null ? "transition-[height] duration-300 ease-out" : ""
      } md:inset-y-3 md:left-3 md:right-auto md:h-auto md:w-[400px] md:rounded-3xl md:transition-none`}
    >
      <div
        role="button"
        aria-label={t.sheet.resize}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onKeyDown={onKeyDown}
        className="flex h-6 shrink-0 cursor-grab touch-none items-center justify-center md:hidden"
      >
        <span className="h-1.5 w-10 rounded-full bg-white/25" />
      </div>
      <div
        ref={content}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-4 md:pt-4"
      >
        {/* Keyed by what is shown, so opening a field or going back to the list rises in. */}
        <div key={contentKey} className="rise-in">
          {children}
        </div>
      </div>
    </section>
  );
}
