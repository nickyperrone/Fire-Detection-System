"use client";

import type { Me } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";

import { BellIcon, PencilPlusIcon, SatelliteIcon } from "./Icons";

const STEPS = [
  { key: "draw", Icon: PencilPlusIcon, tone: "bg-good/15 text-good" },
  { key: "alerts", Icon: BellIcon, tone: "bg-accent/15 text-accent" },
  { key: "watch", Icon: SatelliteIcon, tone: "bg-amber-400/15 text-amber-300" },
] as const;

/** A signed-in account with no fields yet: how to start, and the button to draw the first one
 * (docs/04-frontend.md#first-field). */
export function FirstField({
  me,
  onAddField,
  onNotifications,
}: {
  me: Me;
  onAddField: () => void;
  onNotifications: () => void;
}) {
  const { t } = useLocale();
  const f = t.firstField;

  return (
    <div className="pb-2">
      <div className="flex items-center gap-2.5">
        {/* eslint-disable-next-line @next/next/no-img-element -- a tiny static SVG */}
        <img src="/icon.svg" alt="" className="size-9 rounded-[10px]" />
        <span className="text-[15px] font-semibold tracking-tight">
          Field Watch
        </span>
      </div>

      <h1 className="mt-6 text-[28px] font-semibold leading-[1.1] tracking-tight text-balance">
        {f.title}{" "}
        <span className="bg-gradient-to-r from-accent to-good bg-clip-text text-transparent">
          {f.titleAccent}
        </span>
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-slate-300">
        {f.lead}
      </p>

      <ol className="mt-6 space-y-3.5">
        {STEPS.map(({ key, Icon, tone }, i) => (
          <li key={key} className="flex gap-3">
            <span
              className={`relative grid size-9 shrink-0 place-items-center rounded-xl ${tone}`}
            >
              <Icon className="size-[18px]" />
              <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-surface text-[10px] font-semibold text-slate-200 ring-1 ring-white/15">
                {i + 1}
              </span>
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-slate-100">
                {f.steps[key].title}
              </span>
              <span className="block text-[13px] leading-snug text-muted">
                {f.steps[key].body}
              </span>
            </span>
          </li>
        ))}
      </ol>

      <button
        onClick={onAddField}
        className="mt-7 h-12 w-full rounded-2xl bg-accent font-semibold text-slate-950 shadow-[0_8px_30px_-8px] shadow-accent/60 transition hover:brightness-110"
      >
        {f.cta}
      </button>
      <p className="mt-2 text-center text-xs text-muted">{f.ctaNote}</p>

      {me.telegram.available && !me.telegram.connected && (
        <button
          onClick={onNotifications}
          className="mt-6 flex w-full items-center gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.04] px-3.5 py-3 text-left hover:bg-white/[0.07]"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#229ED9]/20 text-[#5cbfee]">
            <BellIcon className="size-[18px]" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-slate-100">
              {f.telegram.title}
            </span>
            <span className="block text-[13px] leading-snug text-muted">
              {f.telegram.body}
            </span>
          </span>
          <span aria-hidden className="text-muted">
            ›
          </span>
        </button>
      )}
    </div>
  );
}
