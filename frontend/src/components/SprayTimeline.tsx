"use client";

import { useState } from "react";

import type { SprayHour } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { localHourNumber, localTime, ruleSentence } from "@/i18n/text";
import { sprayStatusTone, TONE_HEX } from "@/lib/status";

/** 48 hourly cells colored by spraying status; tapping one explains that hour. */
export function SprayTimeline({ hours }: { hours: SprayHour[] }) {
  const { t } = useLocale();
  const [picked, setPicked] = useState(0);
  if (hours.length === 0)
    return <p className="text-sm text-muted">{t.sprayText.noForecast}.</p>;
  const hour = hours[Math.min(picked, hours.length - 1)];
  const problems = hour.rules.filter((r) => r.status !== "PASS");

  return (
    <div>
      <div
        className="flex gap-px overflow-hidden rounded-lg"
        role="listbox"
        aria-label={t.sprayText.timelineLabel}
      >
        {hours.map((h, i) => (
          <button
            key={h.valid_at}
            role="option"
            aria-selected={i === picked}
            aria-label={`${localTime(t, h.valid_at, true)} ${t.spray[h.status]}`}
            onClick={() => setPicked(i)}
            style={{ background: TONE_HEX[sprayStatusTone(h.status)] }}
            className={`h-9 flex-1 transition-opacity ${i === picked ? "opacity-100" : "opacity-55 hover:opacity-90"}`}
          />
        ))}
      </div>
      <div className="relative mt-1 h-4 text-[11px] text-muted">
        {hours.map((h, i) =>
          localHourNumber(h.valid_at) % 12 === 0 ? (
            <span
              key={h.valid_at}
              className="absolute -translate-x-1/2 whitespace-nowrap"
              style={{ left: `${((i + 0.5) / hours.length) * 100}%` }}
            >
              {localTime(t, h.valid_at, true)}
            </span>
          ) : null,
        )}
      </div>
      <div className="mt-3 rounded-xl bg-white/5 p-3 text-sm">
        <div className="font-semibold">
          {localTime(t, hour.valid_at, true)} · {t.spray[hour.status]}
        </div>
        {problems.length === 0 ? (
          <p className="text-slate-300">{t.sprayText.everyRulePasses}</p>
        ) : (
          <ul className="mt-1 space-y-0.5 text-slate-300">
            {problems.map((rule) => (
              <li key={rule.rule}>{ruleSentence(t, rule)}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
