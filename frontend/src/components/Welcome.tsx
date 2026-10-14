"use client";

import { useLocale } from "@/i18n/LocaleProvider";

import { BoltIcon, FlameIcon, PhotoIcon, SprayIcon } from "./Icons";

const FEATURES = [
  { key: "fire", Icon: FlameIcon, tone: "bg-bad/15 text-bad" },
  { key: "spray", Icon: SprayIcon, tone: "bg-accent/15 text-accent" },
  { key: "storm", Icon: BoltIcon, tone: "bg-amber-400/15 text-amber-300" },
  { key: "photos", Icon: PhotoIcon, tone: "bg-good/15 text-good" },
] as const;

/** What Field Watch is, for someone who has not signed in (docs/04-frontend.md#first-visit). */
export function Welcome({ onSignIn }: { onSignIn: () => void }) {
  const { t } = useLocale();
  const w = t.welcome;

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
        {w.title}{" "}
        <span className="bg-gradient-to-r from-accent to-good bg-clip-text text-transparent">
          {w.titleAccent}
        </span>
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-slate-300">
        {w.lead}
      </p>

      <ul className="mt-6 space-y-3.5">
        {FEATURES.map(({ key, Icon, tone }) => (
          <li key={key} className="flex gap-3">
            <span
              className={`grid size-9 shrink-0 place-items-center rounded-xl ${tone}`}
            >
              <Icon className="size-[18px]" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-slate-100">
                {w.features[key].title}
              </span>
              <span className="block text-[13px] leading-snug text-muted">
                {w.features[key].body}
              </span>
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-7 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
        {w.previewLabel}
      </p>
      <div className="mt-2 overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.04]">
        <div className="px-3.5 pt-3 text-[13px] leading-snug">
          <p className="font-semibold text-slate-100">🔴 {w.preview.badge}</p>
          <p className="mt-0.5 font-semibold text-slate-100">
            {w.preview.headline}
          </p>
          <p className="mt-0.5 text-muted">{w.preview.details}</p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-px border-t border-white/[0.08] bg-white/[0.08] text-center text-xs font-medium text-accent">
          <span className="bg-[#161b23] py-2">📍 {w.preview.directions}</span>
          <span className="bg-[#161b23] py-2">{w.preview.seen}</span>
        </div>
      </div>

      <button
        onClick={onSignIn}
        className="mt-7 h-12 w-full rounded-2xl bg-accent font-semibold text-slate-950 shadow-[0_8px_30px_-8px] shadow-accent/60 transition hover:brightness-110"
      >
        {w.cta}
      </button>
      <p className="mt-2 text-center text-xs text-muted">{w.ctaNote}</p>

      <p className="mt-8 border-t border-white/[0.06] pt-4 text-[11px] leading-relaxed text-muted">
        {w.sources}
      </p>
    </div>
  );
}
