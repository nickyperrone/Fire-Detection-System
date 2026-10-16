"use client";

import { useLandCover } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { formatNumber, localDate } from "@/i18n/text";

// The classes shown, in the order and colors of the bar; the rest join "other".
const SHOWN = [
  { key: "crops", color: "#facc15" },
  { key: "grass", color: "#86efac" },
  { key: "trees", color: "#15803d" },
  { key: "water", color: "#38bdf8" },
  { key: "built", color: "#f87171" },
] as const;
type Shown = (typeof SHOWN)[number]["key"];

type Reason = {
  code: string;
  share?: number;
  low?: number;
  low_on?: string;
  high?: number;
  high_on?: string;
  passes?: number;
};

function reason(t: Messages, r: Reason): string {
  const l = t.landCover.reasons;
  const pct = (share = 0) => formatNumber(t, share * 100);
  const on = (day = "") => localDate(t, day);
  switch (r.code) {
    case "map_crops":
      return l.map_crops(pct(r.share));
    case "map_grass":
      return l.map_grass(pct(r.share));
    case "map_trees":
      return l.map_trees(pct(r.share));
    case "greenness_cycle":
      return l.greenness_cycle(
        formatNumber(t, r.low ?? 0, 2),
        on(r.low_on),
        formatNumber(t, r.high ?? 0, 2),
        on(r.high_on),
        formatNumber(t, r.passes ?? 0),
      );
    default:
      return l.greenness_flat(
        formatNumber(t, r.low ?? 0, 2),
        formatNumber(t, r.high ?? 0, 2),
        formatNumber(t, r.passes ?? 0),
      );
  }
}

function Outline({ color, label }: { color: string; label: string }) {
  return (
    <span className="mr-1 inline-flex items-center gap-1 whitespace-nowrap">
      <span
        aria-hidden
        className="size-2.5 rounded-sm border-2"
        style={{ borderColor: color }}
      />
      {label}
    </span>
  );
}

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
      <div className="rounded-xl bg-white/[0.05] px-3 py-2.5 ring-1 ring-white/10">
        <p className="text-sm font-medium text-slate-100">
          {l.use[cover.land_use.use as keyof typeof l.use] ?? l.use.mixed}
        </p>
        <ul className="mt-1.5 space-y-1 text-[13px] leading-snug text-slate-300">
          {cover.land_use.reasons.map((r, i) => (
            <li key={i}>{reason(t, r as Reason)}</li>
          ))}
        </ul>
      </div>
      {cover.features.length > 0 && (
        <p className="text-[13px] text-slate-300">
          {l.outlined(formatNumber(t, cover.features.length))}{" "}
          <Outline color="#22c55e" label={l.classes.trees} />{" "}
          <Outline color="#f97316" label={l.classes.built} />{" "}
          <Outline color="#38bdf8" label={l.classes.water} />
        </p>
      )}
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
