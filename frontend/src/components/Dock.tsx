"use client";

import { useEffect, useRef, useState } from "react";

import type { Me, PortfolioEntry } from "@/api/client";
import { useHealth } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { formatAge } from "@/i18n/text";

import { AccountMenu } from "./AccountMenu";
import { PEEK_PX } from "./BottomSheet";
import { SatelliteIcon } from "./Icons";

type Props = {
  /** Undefined while the session is being checked. */
  me: Me | null | undefined;
  entries: PortfolioEntry[];
  /** On a phone, the sheet is open above the dock's place. */
  covered: boolean;
  onSignIn: () => void;
};

type Panel = "data" | "account";

type Freshness = { fresh: boolean; short: string; detail: string[] };

function useFreshness(t: Messages): Freshness | null {
  const { data: health, isError } = useHealth();
  if (isError)
    return {
      fresh: false,
      short: t.dock.offline,
      detail: [t.freshness.apiDown],
    };
  if (!health) return null;
  const checks = health.sources
    .filter((s) => s.provider === "firms" && s.last_run_at)
    .map((s) => s.last_run_at!)
    .sort();
  const checked = t.freshness.checked(formatAge(t, checks.at(-1)));
  const pass = health.latest_pass;
  if (health.fire_data_quality === "NO_DATA" || !pass)
    return { fresh: false, short: t.dock.noData, detail: [t.freshness.noData] };
  const age = formatAge(t, pass.acquired_at);
  if (health.fire_data_quality === "STALE")
    return {
      fresh: false,
      short: age,
      detail: [t.freshness.stale(formatAge(t, checks.at(-1)))],
    };
  return {
    fresh: true,
    short: age,
    detail: [
      t.freshness.lastPass(`${pass.sensor} ${pass.satellite}`, age),
      checked,
      ...(health.fire_data_quality === "PARTIAL" ? [t.freshness.partial] : []),
    ],
  };
}

const SEGMENT =
  "flex h-9 items-center gap-2 rounded-full px-3 text-xs font-medium text-slate-200 hover:bg-white/10 aria-expanded:bg-white/15";

/** A floating glass bar at the bottom: data freshness, the portfolio, language and account
 * (docs/04-frontend.md#visual-style). */
export function Dock({ me, entries, covered, onSignIn }: Props) {
  const { t, locale, setLocale } = useLocale();
  const freshness = useFreshness(t);
  const [panel, setPanel] = useState<Panel | null>(null);
  const dock = useRef<HTMLDivElement>(null);

  // A tap anywhere else, or Escape, closes the open panel.
  useEffect(() => {
    if (!panel) return;
    const onPointer = (e: PointerEvent) => {
      if (!dock.current?.contains(e.target as Node)) setPanel(null);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPanel(null);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [panel]);

  const toggle = (next: Panel) => setPanel((p) => (p === next ? null : next));
  const fields = entries.filter((e) => e.kind === "FIELD");
  const hectares = new Intl.NumberFormat(t.intl, {
    maximumFractionDigits: 0,
  }).format(fields.reduce((sum, e) => sum + e.hectares, 0));

  const content =
    panel === "data" && freshness ? (
      <div className="text-sm">
        <p className="text-xs text-muted">{t.dock.data}</p>
        {freshness.detail.map((line) => (
          <p key={line} className="mt-1 text-slate-200">
            {line}
          </p>
        ))}
      </div>
    ) : panel === "account" && me ? (
      <AccountMenu me={me} />
    ) : null;

  return (
    <div
      ref={dock}
      role="toolbar"
      aria-label={t.dock.label}
      style={{ "--peek": `${PEEK_PX}px` } as React.CSSProperties}
      className={`fixed bottom-[calc(var(--peek)+10px)] left-1/2 z-10 -translate-x-1/2 transition-[translate,opacity] duration-300 ease-out md:bottom-4 md:left-[calc(50%+206px)] ${
        covered
          ? "pointer-events-none translate-y-4 opacity-0 md:pointer-events-auto md:translate-y-0 md:opacity-100"
          : ""
      }`}
    >
      {content && (
        <div
          key={panel}
          className="liquid pop-up absolute bottom-full left-1/2 mb-2 w-max max-w-[calc(100vw-24px)] -translate-x-1/2 rounded-2xl p-3"
        >
          {content}
        </div>
      )}

      <div className="liquid rise-in flex items-center gap-0.5 rounded-full p-1">
        {freshness && (
          <button
            aria-expanded={panel === "data"}
            aria-label={`${t.dock.data}: ${freshness.detail.join(", ")}`}
            onClick={() => toggle("data")}
            className={SEGMENT}
          >
            <span
              className={`relative size-2 rounded-full ${
                freshness.fresh ? "live bg-good" : "bg-unknown"
              }`}
            />
            <SatelliteIcon className="size-3.5 text-muted" />
            <span className="whitespace-nowrap">{freshness.short}</span>
          </button>
        )}

        {me && fields.length > 0 && (
          <>
            <Divider />
            <span className="whitespace-nowrap px-3 text-xs text-slate-300 tabular-nums">
              {t.dock.fields(fields.length, hectares)}
            </span>
          </>
        )}

        <Divider />
        <button
          aria-label={t.dock.switchTo}
          title={t.dock.switchTo}
          onClick={() => setLocale(locale === "es" ? "en" : "es")}
          className={`${SEGMENT} uppercase`}
        >
          {locale}
        </button>

        {me !== undefined && (
          <>
            <Divider />
            {me ? (
              <button
                aria-expanded={panel === "account"}
                aria-label={t.signIn.account(me.email)}
                onClick={() => toggle("account")}
                className="relative grid size-9 place-items-center rounded-full bg-white/10 text-xs font-semibold uppercase text-white hover:bg-white/20 aria-expanded:bg-white/25"
              >
                {me.email[0]}
                <span className="absolute bottom-0.5 right-0.5 size-2.5 rounded-full border-2 border-[#1b2028] bg-good" />
              </button>
            ) : (
              <button
                onClick={onSignIn}
                className={`${SEGMENT} font-semibold text-accent`}
              >
                {t.signIn.button}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Divider() {
  return <span aria-hidden className="h-4 w-px shrink-0 bg-white/12" />;
}
