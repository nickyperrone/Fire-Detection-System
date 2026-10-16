"use client";

import { useLandCover } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatNumber } from "@/i18n/text";

// The classes shown, in the order and colors of the bar; the rest join "other".
const SHOWN = [
  { key: "crops", color: "#facc15" },
  { key: "grass", color: "#86efac" },
  { key: "trees", color: "#15803d" },
  { key: "water", color: "#38bdf8" },
  { key: "built", color: "#f87171" },
] as const;
type Shown = (typeof SHOWN)[number]["key"];

/** What covers the field, from ESA WorldCover, and what it does to fire danger
 * (docs/15-land-cover.md). */
export function LandCoverSection({ territoryId }: { territoryId: number }) {
  const { t } = useLocale();
  const { data: cover, isPending } = useLandCover(territoryId);
  const l = t.landCover;

  if (isPending) return null;
  if (!cover) return <p className="text-sm text-slate-400">{l.pending}</p>;

  const share = (key: Shown) =>
    key === "trees"
      ? cover.trees_share
      : key === "water"
        ? (cover.shares.water ?? 0) + (cover.shares.wetland ?? 0)
        : (cover.shares[key] ?? 0);
  const parts = SHOWN.map((s) => ({ ...s, share: share(s.key) })).filter(
    (p) => p.share >= 0.01,
  );
  const other = Math.max(0, 1 - parts.reduce((sum, p) => sum + p.share, 0));

  return (
    <div className="space-y-2">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-white/10">
        {parts.map((p) => (
          <span
            key={p.key}
            style={{ width: `${p.share * 100}%`, background: p.color }}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-200">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{ background: p.color }}
            />
            {l.classes[p.key]} {formatNumber(t, p.share * 100)} %
          </li>
        ))}
        {other >= 0.01 && (
          <li className="text-muted">
            {l.other} {formatNumber(t, other * 100)} %
          </li>
        )}
      </ul>
      {cover.has_buildings && (
        <p className="text-sm text-slate-100">
          {cover.built_m2 > 0
            ? l.buildingsInside(formatNumber(t, cover.built_m2))
            : l.buildingsNearby}
        </p>
      )}
      {cover.wooded && <p className="text-sm text-slate-100">{l.wooded}</p>}
      <p className="text-[11px] text-muted">{l.source}</p>
    </div>
  );
}
