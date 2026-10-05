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
import { patchLine } from "./Anomalies";
import { StatusChip } from "./StatusChip";

/** The most useful single sentence about a field, in the order of attention: a fire, lightning,
 * the largest unusual patch, then why not to spray. */
export function headline(t: Messages, entry: PortfolioEntry): string {
  const { fire, spray, lightning, anomaly } = entry;
  if (fire.severity || fire.data_quality === "NO_DATA")
    return fireSentence(t, fire);
  if (lightning.flashes > 0) return lightningSentence(t, entry);
  if (anomaly.patches.length > 0) return patchLine(t, anomaly.patches[0]);
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

/** Fire and spraying chips, plus a lightning chip only when there is lightning nearby.
 * `onlyProblems` leaves the green ones out, for lists where "fine" is the quiet default. */
export function FieldChips({
  entry,
  onlyProblems = false,
}: {
  entry: PortfolioEntry;
  onlyProblems?: boolean;
}) {
  const { t } = useLocale();
  const fire = fireTone(entry.fire);
  const spray = sprayTone(entry.spray);
  return (
    <div className="flex flex-wrap gap-1.5">
      {!(onlyProblems && fire === "good") && (
        <StatusChip tone={fire} icon={<FlameIcon className="size-3.5" />}>
          {fireLabel(t, entry.fire)}
        </StatusChip>
      )}
      {!(onlyProblems && spray === "good") && (
        <StatusChip tone={spray} icon={<SprayIcon className="size-3.5" />}>
          {sprayLabel(t, entry.spray)}
        </StatusChip>
      )}
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
