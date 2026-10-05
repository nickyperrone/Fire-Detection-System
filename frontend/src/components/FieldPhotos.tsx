"use client";

/* eslint-disable @next/next/no-img-element -- the photos are private: next/image would fetch them
 * from the server without the session cookie. They are small PNGs already. */

import { useEffect, useRef, useState } from "react";

import {
  snapshotUrl,
  type Snapshot,
  type Snapshots,
  type SnapshotView,
} from "@/api/client";
import { useSnapshots } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { formatNumber, localDate } from "@/i18n/text";
import { monthStarts, newestClear } from "@/lib/photos";

import { ChevronIcon, CloseIcon, CompareIcon, ExpandIcon } from "./Icons";

const VIEWS: SnapshotView[] = ["true_color", "greenness"];
/** The satellite photos of a field, one per clear pass (docs/12-field-page.md#satellite-photos).
 * On a lot's page they are its field's photos, with the lot highlighted. */
export function FieldPhotos({ territoryId }: { territoryId: number }) {
  const { t } = useLocale();
  const photos = useSnapshots(territoryId);
  const [view, setView] = useState<SnapshotView>("true_color");
  // null: the newest clear photo, which a new clear pass replaces.
  const [picked, setPicked] = useState<number | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  const [large, setLarge] = useState(false);

  if (photos.isPending)
    return (
      <div className="aspect-square animate-pulse rounded-2xl bg-white/5" />
    );
  if (photos.isError)
    return <p className="text-sm text-bad">{t.app.apiDown}</p>;
  const { snapshots } = photos.data;
  if (snapshots.length === 0)
    return <p className="text-sm text-slate-300">{t.photos.none}</p>;

  const current = Math.min(
    picked ?? newestClear(snapshots),
    snapshots.length - 1,
  );
  const step = (by: number) =>
    setPicked(Math.max(0, Math.min(snapshots.length - 1, current + by)));
  const toggleCompare = () =>
    setBefore((b) => (b === null ? (current > 0 ? 0 : null) : null));

  const viewer = (size: "panel" | "large") => (
    <Viewer
      data={photos.data}
      current={current}
      before={before}
      view={view}
      highlight={territoryId}
      size={size}
      onStep={step}
    />
  );

  const controls = (
    <div className="flex items-center gap-2">
      <div
        role="radiogroup"
        aria-label={t.photos.viewLabel}
        className="flex rounded-full bg-white/[0.07] p-0.5"
      >
        {VIEWS.map((option) => (
          <button
            key={option}
            role="radio"
            aria-checked={view === option}
            onClick={() => setView(option)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              view === option ? "bg-white text-slate-950" : "text-slate-300"
            }`}
          >
            {t.photos.views[option]}
          </button>
        ))}
      </div>
      <button
        aria-pressed={before !== null}
        disabled={snapshots.length < 2}
        onClick={toggleCompare}
        className="ml-auto flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium text-slate-300 hover:bg-white/10 disabled:opacity-40 aria-pressed:bg-white aria-pressed:text-slate-950"
      >
        <CompareIcon className="size-3.5" />
        {t.photos.compare}
      </button>
    </div>
  );

  const compareWith = before !== null && (
    <label className="flex items-center gap-2 text-xs text-muted">
      {t.photos.before}
      <select
        value={before}
        onChange={(e) => setBefore(Number(e.target.value))}
        className="rounded-full bg-white/[0.07] px-2.5 py-1 text-slate-200 outline-none focus:ring-2 focus:ring-accent/60"
      >
        {snapshots.map((s, i) => (
          <option key={s.date} value={i} disabled={i === current}>
            {localDate(t, s.date)} {s.date.slice(0, 4)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="space-y-3">
      <div className="relative">
        {viewer("panel")}
        <button
          aria-label={t.photos.fullscreen}
          onClick={() => setLarge(true)}
          className="liquid absolute right-2 top-2 grid size-8 place-items-center rounded-full text-white"
        >
          <ExpandIcon className="size-4" />
        </button>
      </div>
      <Caption t={t} photo={snapshots[current]} />
      {controls}
      {compareWith}
      {view === "greenness" && <Legend t={t} />}
      <GreennessChart
        t={t}
        snapshots={snapshots}
        current={current}
        before={before}
        onPick={setPicked}
      />
      <Strip
        t={t}
        fieldId={photos.data.field_id}
        snapshots={snapshots}
        current={current}
        view={view}
        onPick={setPicked}
      />
      <p className="text-[11px] text-muted">
        {t.photos.count(snapshots.length)} · {t.photos.source}
      </p>

      {large && (
        <FullScreen t={t} onClose={() => setLarge(false)} onStep={step}>
          {viewer("large")}
          <div className="mx-auto mt-3 w-full max-w-xl space-y-3">
            <Caption t={t} photo={snapshots[current]} />
            {controls}
            {compareWith}
            <Strip
              t={t}
              fieldId={photos.data.field_id}
              snapshots={snapshots}
              current={current}
              view={view}
              onPick={setPicked}
            />
          </div>
        </FullScreen>
      )}
    </div>
  );
}

type ViewerProps = {
  data: Snapshots;
  current: number;
  before: number | null;
  view: SnapshotView;
  /** The field or lot whose page this is: drawn bolder than the rest. */
  highlight: number;
  size: "panel" | "large";
  onStep: (by: number) => void;
};

/** The photo with every outline on top; in compare mode, a divider wipes between two dates. */
function Viewer({
  data,
  current,
  before,
  view,
  highlight,
  size,
  onStep,
}: ViewerProps) {
  const { t } = useLocale();
  const [split, setSplit] = useState(50);
  const { field_id: fieldId, width, height, snapshots, outlines } = data;
  const photo = snapshots[current];
  const earlier = before !== null ? snapshots[before] : null;
  const isLot = highlight !== fieldId;

  return (
    <div
      className={`relative overflow-hidden rounded-2xl bg-black/50 ${
        size === "large" ? "mx-auto" : ""
      }`}
      style={{
        aspectRatio: `${width} / ${height}`,
        width:
          size === "large"
            ? `min(100%, calc(68vh * ${width / height}))`
            : undefined,
      }}
    >
      <img
        key={`${photo.date}-${view}`}
        src={snapshotUrl(fieldId, photo.date, view)}
        alt={t.photos.photoOf(localDate(t, photo.date))}
        className="fade-in absolute inset-0 size-full"
      />
      {earlier && (
        <img
          key={`before-${earlier.date}-${view}`}
          src={snapshotUrl(fieldId, earlier.date, view)}
          alt={t.photos.photoOf(localDate(t, earlier.date))}
          className="absolute inset-0 size-full"
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-0 size-full"
        aria-hidden
      >
        {outlines.map((o) => {
          const main = o.territory_id === highlight;
          return (
            <path
              key={o.territory_id}
              d={o.path}
              fill={main && isLot ? "rgb(255 255 255 / 0.12)" : "none"}
              stroke="white"
              strokeOpacity={main ? 0.95 : 0.55}
              strokeWidth={main ? 2 : 1}
              strokeDasharray={
                o.kind === "SECTION" && !main ? "4 3" : undefined
              }
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      {earlier && (
        <>
          <div
            className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_12px_rgb(0_0_0/0.6)]"
            style={{ left: `${split}%` }}
          >
            <span className="liquid absolute top-1/2 left-1/2 grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full">
              <CompareIcon className="size-4 text-white" />
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={split}
            onChange={(e) => setSplit(Number(e.target.value))}
            aria-label={t.photos.divider}
            className="absolute inset-0 size-full cursor-ew-resize opacity-0"
          />
          <DateTag side="left">{localDate(t, earlier.date)}</DateTag>
          <DateTag side="right">{localDate(t, photo.date)}</DateTag>
        </>
      )}

      {!earlier && (
        <>
          <StepButton
            label={t.photos.previous}
            side="left"
            disabled={current === 0}
            onClick={() => onStep(-1)}
          />
          <StepButton
            label={t.photos.next}
            side="right"
            disabled={current === snapshots.length - 1}
            onClick={() => onStep(1)}
          />
        </>
      )}
    </div>
  );
}

function DateTag({
  side,
  children,
}: {
  side: "left" | "right";
  children: React.ReactNode;
}) {
  return (
    <span
      className={`liquid pointer-events-none absolute bottom-2 rounded-full px-2 py-0.5 text-[11px] font-medium text-white ${
        side === "left" ? "left-2" : "right-2"
      }`}
    >
      {children}
    </span>
  );
}

function StepButton({
  label,
  side,
  disabled,
  onClick,
}: {
  label: string;
  side: "left" | "right";
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`liquid absolute top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full text-white disabled:opacity-0 ${
        side === "left" ? "left-2" : "right-2"
      }`}
    >
      <ChevronIcon
        className={`size-4 ${side === "left" ? "rotate-180" : ""}`}
      />
    </button>
  );
}

function Caption({ t, photo }: { t: Messages; photo: Snapshot }) {
  const year = photo.date.slice(0, 4);
  const clouds = Math.round(photo.cloud_share * 100);
  return (
    <div className="flex items-baseline justify-between gap-3">
      <p className="text-lg font-semibold tracking-tight">
        {localDate(t, photo.date)}{" "}
        <span className="font-normal text-muted">{year}</span>
      </p>
      <p className="flex items-center gap-2 text-xs text-slate-300 tabular-nums">
        {photo.ndvi_mean !== null && (
          <span>{t.photos.meanNdvi(formatNumber(t, photo.ndvi_mean, 2))}</span>
        )}
        <span className="rounded-full bg-white/[0.07] px-2 py-0.5">
          {clouds < 1 ? t.photos.clear : t.photos.clouds(String(clouds))}
        </span>
      </p>
    </div>
  );
}

function Legend({ t }: { t: Messages }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted">
      <span>{t.photos.bare}</span>
      <span className="h-1.5 flex-1 rounded-full bg-[linear-gradient(90deg,#785c3e,#c4aa68_30%,#8eb654_55%,#3a8c42_80%,#165830)]" />
      <span>{t.photos.dense}</span>
    </div>
  );
}

const CHART_H = 64;
const PAD = 6;

/** Mean NDVI of every kept pass: sowing, growth and harvest as the line rising and falling. */
function GreennessChart({
  t,
  snapshots,
  current,
  before,
  onPick,
}: {
  t: Messages;
  snapshots: Snapshot[];
  current: number;
  before: number | null;
  onPick: (index: number) => void;
}) {
  const points = snapshots
    .map((s, index) => ({ index, s }))
    .filter(({ s }) => s.ndvi_mean !== null);
  if (points.length < 2) return null;
  const day = (s: Snapshot) => new Date(`${s.date}T00:00:00Z`).getTime();
  const first = day(snapshots[0]);
  const span = Math.max(day(snapshots.at(-1)!) - first, 1);
  // In hundredths of the width, so the chart stretches with the panel.
  const x = (s: Snapshot) => PAD + ((day(s) - first) / span) * (100 - 2 * PAD);
  const y = (ndvi: number) =>
    PAD + (1 - Math.max(0, Math.min(ndvi, 1))) * (CHART_H - 2 * PAD);
  const line = points
    .map(({ s }, i) => `${i ? "L" : "M"}${x(s)} ${y(s.ndvi_mean!)}`)
    .join("");
  const area = `${line}L${x(points.at(-1)!.s)} ${CHART_H}L${x(points[0].s)} ${CHART_H}Z`;
  const months = monthStarts(snapshots[0].date, snapshots.at(-1)!.date);

  return (
    <figure className="rounded-2xl bg-white/[0.04] px-2 pb-1 pt-2">
      <figcaption className="px-1 text-[11px] font-medium text-muted">
        {t.photos.over}
      </figcaption>
      <div className="relative" style={{ height: CHART_H }}>
        <svg
          viewBox={`0 0 100 ${CHART_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 size-full"
          aria-hidden
        >
          <defs>
            <linearGradient id="greenness-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#4ade80" stopOpacity="0.28" />
              <stop offset="1" stopColor="#4ade80" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill="url(#greenness-fill)" />
          <path
            d={line}
            fill="none"
            stroke="#4ade80"
            strokeWidth={1.5}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {/* Points as buttons on top: round at any width, and each one opens its photo. */}
        {points.map(({ index, s }) => {
          const state =
            index === current ? "current" : index === before ? "before" : "";
          return (
            <button
              key={s.date}
              aria-label={`${t.photos.photoOf(localDate(t, s.date))} · ${t.photos.meanNdvi(formatNumber(t, s.ndvi_mean!, 2))}`}
              aria-current={index === current}
              onClick={() => onPick(index)}
              className="group absolute grid size-6 -translate-x-1/2 -translate-y-1/2 place-items-center"
              style={{ left: `${x(s)}%`, top: y(s.ndvi_mean!) }}
            >
              <span
                className={`block rounded-full transition-[width,height] ${
                  state === "current"
                    ? "size-3 bg-white ring-4 ring-white/25"
                    : state === "before"
                      ? "size-2.5 bg-accent ring-4 ring-accent/25"
                      : "size-1.5 bg-[#4ade80] group-hover:size-2.5"
                }`}
              />
            </button>
          );
        })}
      </div>
      <div className="relative h-4 text-[10px] text-muted">
        {months.map((month) => {
          const left =
            PAD +
            ((new Date(`${month}T00:00:00Z`).getTime() - first) / span) *
              (100 - 2 * PAD);
          return (
            <span
              key={month}
              className="absolute -translate-x-1/2"
              style={{ left: `${left}%` }}
            >
              {new Intl.DateTimeFormat(t.intl, {
                month: "short",
                timeZone: "UTC",
              }).format(new Date(`${month}T00:00:00Z`))}
            </span>
          );
        })}
      </div>
    </figure>
  );
}

function Strip({
  t,
  fieldId,
  snapshots,
  current,
  view,
  onPick,
}: {
  t: Messages;
  fieldId: number;
  snapshots: Snapshot[];
  current: number;
  view: SnapshotView;
  onPick: (index: number) => void;
}) {
  const strip = useRef<HTMLDivElement>(null);
  const selected = useRef<HTMLButtonElement>(null);
  // Centers the open photo in the strip. scrollIntoView would also scroll the panel around it.
  useEffect(() => {
    const row = strip.current;
    const thumb = selected.current;
    if (!row || !thumb) return;
    row.scrollTo({
      left: thumb.offsetLeft - (row.clientWidth - thumb.clientWidth) / 2,
      behavior: "smooth",
    });
  }, [current]);

  return (
    <div
      ref={strip}
      className="no-scrollbar relative -mx-1 flex gap-2 overflow-x-auto px-1 py-1"
    >
      {snapshots.map((s, index) => (
        <button
          key={s.date}
          ref={index === current ? selected : undefined}
          aria-label={t.photos.photoOf(localDate(t, s.date))}
          aria-current={index === current}
          onClick={() => onPick(index)}
          className="shrink-0 text-center"
        >
          <img
            src={snapshotUrl(fieldId, s.date, view)}
            alt=""
            loading="lazy"
            className={`size-14 rounded-lg object-cover transition-[outline-color,opacity] ${
              index === current
                ? "outline-2 outline-offset-2 outline-white"
                : "opacity-70 outline-2 outline-transparent hover:opacity-100"
            }`}
          />
          <span
            className={`mt-1 block text-[10px] tabular-nums ${index === current ? "text-white" : "text-muted"}`}
          >
            {localDate(t, s.date)}
          </span>
        </button>
      ))}
    </div>
  );
}

function FullScreen({
  t,
  onClose,
  onStep,
  children,
}: {
  t: Messages;
  onClose: () => void;
  onStep: (by: number) => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") onStep(-1);
      if (e.key === "ArrowRight") onStep(1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, onStep]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.photos.fullscreen}
      className="fade-in fixed inset-0 z-40 overflow-y-auto bg-[#07090c]/90 p-4 backdrop-blur-xl md:p-8"
    >
      <button
        aria-label={t.photos.close}
        onClick={onClose}
        className="liquid fixed right-4 top-4 z-10 grid size-10 place-items-center rounded-full text-white"
      >
        <CloseIcon className="size-5" />
      </button>
      <div className="mx-auto max-w-5xl pt-10">{children}</div>
    </div>
  );
}
