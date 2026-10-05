"use client";

import type { PortfolioEntry } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { direction, formatNumber, localDate } from "@/i18n/text";

type Anomaly = PortfolioEntry["anomaly"];
type AnomalyPatch = Anomaly["patches"][number];

/** "Less green in 13.4 ha to the S of Lote 3". */
export function patchLine(t: Messages, patch: AnomalyPatch): string {
  const place =
    patch.where === "center"
      ? t.anomaly.center
      : t.anomaly.toward(direction(t, patch.where));
  const where = patch.lot ? `${place}${t.anomaly.ofLot(patch.lot)}` : place;
  return t.anomaly.line(
    t.anomaly.kinds[patch.kind] ?? patch.kind,
    formatNumber(t, patch.area_ha, 1),
    where,
  );
}

/** The card's "Something unusual" section (docs/11-field-anomalies.md#in-the-product). */
export function AnomalySection({ anomaly }: { anomaly: Anomaly }) {
  const { t } = useLocale();
  const seen = anomaly.observed_on ? localDate(t, anomaly.observed_on) : "";
  const patches = (
    <ul className="mt-1 space-y-0.5">
      {anomaly.patches.map((patch, i) => (
        <li key={i} className="font-medium text-bad">
          {patchLine(t, patch)}
        </li>
      ))}
    </ul>
  );
  let body: React.ReactNode;
  if (anomaly.data_quality === "GOOD") {
    body = anomaly.patches.length ? (
      <>
        <p className="text-sm text-slate-300">{t.anomaly.seenOn(seen)}</p>
        {patches}
      </>
    ) : (
      <p className="font-medium text-good">{t.anomaly.nothing(seen)}</p>
    );
  } else if (anomaly.data_quality === "CLOUD_OBSCURED") {
    body = (
      <>
        <p className="text-sm text-slate-300">
          {anomaly.patches.length
            ? t.anomaly.cloudy(seen)
            : t.anomaly.cloudyNothing(seen)}
        </p>
        {anomaly.patches.length > 0 && patches}
      </>
    );
  } else {
    body = (
      <p className="text-sm text-slate-400">
        {anomaly.data_quality === "PARTIAL"
          ? t.anomaly.partial
          : t.anomaly.noData}
      </p>
    );
  }
  return (
    <div>
      {body}
      <p className="mt-2 text-[11px] leading-4 text-muted">{t.anomaly.note}</p>
    </div>
  );
}
