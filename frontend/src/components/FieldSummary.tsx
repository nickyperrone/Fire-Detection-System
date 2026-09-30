"use client";

import type { PortfolioEntry } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { fireLabel, fireSentence, localTime, ruleSentence, sprayLabel } from "@/i18n/text";
import { fireTone, sprayTone } from "@/lib/status";

import { FlameIcon, SprayIcon } from "./Icons";
import { StatusChip } from "./StatusChip";

/** The most useful single sentence about a field: a fire first, then why not to spray. */
export function headline(t: Messages, entry: PortfolioEntry): string {
  const { fire, spray } = entry;
  if (fire.severity || fire.data_quality === "NO_DATA") return fireSentence(t, fire);
  if (!spray.status) return t.sprayText.noForecast;
  if (spray.status === "FAVORABLE") return t.sprayText.allPass;
  const window = spray.next_favorable;
  const next = window ? t.sprayText.nextWindow(localTime(t, window[0], true)) : t.sprayText.noWindow;
  return spray.problems[0] ? `${ruleSentence(t, spray.problems[0])} · ${next}` : next;
}

/** Two chips, fire and spraying, in the same order and colors everywhere. */
export function FieldChips({ entry }: { entry: PortfolioEntry }) {
  const { t } = useLocale();
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatusChip tone={fireTone(entry.fire)} icon={<FlameIcon className="size-3.5" />}>
        {fireLabel(t, entry.fire)}
      </StatusChip>
      <StatusChip tone={sprayTone(entry.spray)} icon={<SprayIcon className="size-3.5" />}>
        {sprayLabel(t, entry.spray)}
      </StatusChip>
    </div>
  );
}
