"use client";

import type { PortfolioEntry } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import {
  fireLabel,
  fireSentence,
  formatDistance,
  localTime,
  ruleSentence,
  sprayLabel,
} from "@/i18n/text";
import { fireTone, sprayTone } from "@/lib/status";

import {
  BoltIcon,
  FlameIcon,
  ForecastIcon,
  PatchIcon,
  SprayIcon,
} from "./Icons";
import { StatusChip } from "./StatusChip";

/** The most useful single sentence about a field: a fire first, then why not to spray. */
export function headline(t: Messages, entry: PortfolioEntry): string {
  const { fire, spray, lightning } = entry;
  if (fire.severity || fire.data_quality === "NO_DATA")
    return fireSentence(t, fire);
  if (lightning.flashes > 0) return lightningSentence(t, entry);
  if (!spray.status) return t.sprayText.noForecast;
  if (spray.status === "FAVORABLE") return t.sprayText.allPass;
  const window = spray.next_favorable;
  const next = window
    ? t.sprayText.nextWindow(localTime(t, window[0], true))
    : t.sprayText.noWindow;
  return spray.problems[0]
    ? `${ruleSentence(t, spray.problems[0])} · ${next}`
    : next;
}

export function lightningSentence(t: Messages, entry: PortfolioEntry): string {
  const { lightning } = entry;
  if (lightning.flashes === 0)
    return t.lightning.noneSentence(lightning.window_minutes);
  return t.lightning.sentence(
    lightning.flashes,
    formatDistance(t, lightning.nearest_m),
    lightning.window_minutes,
  );
}

/** Fire and spraying chips, plus a lightning chip only when there is lightning nearby. */
export function FieldChips({ entry }: { entry: PortfolioEntry }) {
  const { t } = useLocale();
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatusChip
        tone={fireTone(entry.fire)}
        icon={<FlameIcon className="size-3.5" />}
      >
        {fireLabel(t, entry.fire)}
      </StatusChip>
      <StatusChip
        tone={sprayTone(entry.spray)}
        icon={<SprayIcon className="size-3.5" />}
      >
        {sprayLabel(t, entry.spray)}
      </StatusChip>
      {["HIGH", "VERY_HIGH"].includes(entry.forecast.days[0]?.band ?? "") && (
        <StatusChip tone="bad" icon={<ForecastIcon className="size-3.5" />}>
          {t.forecast.chip(t.forecast.band[entry.forecast.days[0].band])}
        </StatusChip>
      )}
      {entry.lightning.flashes > 0 && (
        <StatusChip tone="bad" icon={<BoltIcon className="size-3.5" />}>
          {t.lightning.count(entry.lightning.flashes)}
        </StatusChip>
      )}
      {entry.anomaly.patches.length > 0 && (
        <StatusChip tone="bad" icon={<PatchIcon className="size-3.5" />}>
          {t.anomaly.chip(entry.anomaly.patches.length)}
        </StatusChip>
      )}
    </div>
  );
}
