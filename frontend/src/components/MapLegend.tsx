"use client";

import { useState, useSyncExternalStore } from "react";

import { useLocale } from "@/i18n/LocaleProvider";
import { formatAge } from "@/i18n/text";
import { type Tone, TONE_HEX } from "@/lib/status";
import type { ColorBy } from "@/lib/useUrlState";

import { RISK_BANDS } from "./map/overlay";

import { ChevronIcon, PauseIcon, PlayIcon, PlusIcon } from "./Icons";

type Props = {
  /** The user has fields: the state and tag legend applies. */
  showFields: boolean;
  /** The fire risk layer is on: its scale is shown too. */
  showRisk: boolean;
  /** The clouds and rain layer is on, with the time of its scan once it has loaded. */
  weather: WeatherLoop | null;
  colorBy: ColorBy;
  onColorBy: (colorBy: ColorBy) => void;
  /** Tags in use, in the order that decides a field's color, with their colors. */
  tags: { label: string; color: string }[];
  /** A field is open, so "+ Etiqueta" can tag it. */
  canTag: boolean;
  onAddTag: () => void;
};

const STATES: { tone: Tone; name: "danger" | "clear" | "unknown" }[] = [
  { tone: "bad", name: "danger" },
  { tone: "good", name: "clear" },
  { tone: "unknown", name: "unknown" },
];
// The colors the worker paints (backend/app/vision/weather_layer.py), lightest rain first.
const WEATHER_SWATCHES = [
  { name: "clouds", color: "rgb(240 244 248 / 0.35)" },
  { name: "light", color: "rgb(96 165 250)" },
  { name: "moderate", color: "rgb(37 99 235)" },
  { name: "heavy", color: "rgb(168 85 247)" },
] as const;

/** The clouds and rain loop, as the legend shows and steers it. */
type WeatherLoop = {
  /** The scan of the frame on screen; null while the frames load. */
  scannedAt: string | null;
  playing: boolean;
  onTogglePlay: () => void;
  shown: number;
  count: number;
};
const WIDE = "(min-width: 768px)";

function subscribeToWidth(onChange: () => void): () => void {
  const query = window.matchMedia(WIDE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

// Past this many tags the legend says "+N" instead of growing over the map.
const SHOWN_TAGS = 5;

/** What the field colors mean, and the switch between coloring by state and by tag
 * (docs/01-product.md#field-states). */
export function MapLegend({
  showFields,
  showRisk,
  weather,
  colorBy,
  onColorBy,
  tags,
  canTag,
  onAddTag,
}: Props) {
  const { t } = useLocale();
  // Open on a computer; on a phone it starts folded to its switch, so the map stays in view.
  // Until the user folds or opens it, the screen width decides.
  const wide = useSyncExternalStore(
    subscribeToWidth,
    () => window.matchMedia(WIDE).matches,
    () => false,
  );
  const [choice, setChoice] = useState<boolean | null>(null);
  const open = choice ?? wide;

  return (
    <section
      aria-label={t.legend.label}
      className="liquid w-fit max-w-full rounded-2xl p-1.5 text-xs"
    >
      <div className="flex items-center gap-1">
        {showFields ? (
          <div
            role="radiogroup"
            aria-label={t.colorBy.label}
            className="flex flex-1 rounded-full bg-black/25 p-0.5"
          >
            {(["status", "tags"] as const).map((option) => (
              <button
                key={option}
                role="radio"
                aria-checked={colorBy === option}
                onClick={() => onColorBy(option)}
                className={`flex-1 rounded-full px-3 py-1.5 font-medium ${
                  colorBy === option
                    ? "bg-white text-slate-950"
                    : "text-slate-300 hover:text-white"
                }`}
              >
                {t.colorBy[option]}
              </button>
            ))}
          </div>
        ) : (
          <span className="px-2 font-medium text-slate-200">
            {t.legend.label}
          </span>
        )}
        <button
          aria-expanded={open}
          aria-label={t.legend.toggle}
          onClick={() => setChoice(!open)}
          className="grid size-8 shrink-0 place-items-center rounded-full text-muted hover:bg-white/10 hover:text-white"
        >
          <ChevronIcon
            className={`size-3.5 transition-transform ${open ? "-rotate-90" : "rotate-90"}`}
          />
        </button>
      </div>
      {open && showFields && (
        <FieldColors
          colorBy={colorBy}
          tags={tags}
          canTag={canTag}
          onAddTag={onAddTag}
        />
      )}
      {open && showRisk && (
        <div
          className={`px-2 pb-1 pt-1.5 ${showFields ? "mt-1 border-t border-white/10" : ""}`}
        >
          <p className="text-[11px] text-muted">{t.legend.riskTomorrow}</p>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-slate-200">
            {RISK_BANDS.map(({ band, color, opacity }) => (
              <span key={band} className="flex items-center gap-1.5">
                <span
                  aria-hidden
                  className="block size-2.5 rounded-sm ring-1 ring-white/20"
                  // Twice the map's opacity: a small swatch needs more color to read.
                  style={{
                    background: color,
                    opacity: Math.min(1, opacity * 2),
                  }}
                />
                {t.forecast.band[band]}
              </span>
            ))}
          </div>
        </div>
      )}
      {weather && (
        <div
          className={`px-2 pb-1 pt-1.5 ${showFields || showRisk ? "mt-1 border-t border-white/10" : ""}`}
        >
          {/* The loop's controls stay visible with the legend folded: it is moving on the map. */}
          <div className="flex items-center gap-2">
            <button
              aria-label={
                weather.playing ? t.weatherLayer.pause : t.weatherLayer.play
              }
              onClick={weather.onTogglePlay}
              disabled={weather.count < 2}
              className="grid size-7 shrink-0 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20 disabled:opacity-40"
            >
              {weather.playing ? (
                <PauseIcon className="size-3.5" />
              ) : (
                <PlayIcon className="size-3.5" />
              )}
            </button>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[11px] text-slate-200 tabular-nums">
                {weather.scannedAt
                  ? t.weatherLayer.title(formatAge(t, weather.scannedAt))
                  : t.weatherLayer.layer}
              </p>
              {/* Where the frame on screen sits in the two hours, oldest on the left. */}
              <div className="mt-1 flex gap-0.5" aria-hidden>
                {Array.from({ length: weather.count }, (_, i) => (
                  <span
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-colors ${
                      i === weather.shown ? "bg-white" : "bg-white/20"
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>
          {open && (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-slate-200">
              {WEATHER_SWATCHES.map(({ name, color }) => (
                <span key={name} className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="block size-2.5 rounded-sm ring-1 ring-white/20"
                    style={{ background: color }}
                  />
                  {t.weatherLayer[name]}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/** What each field color means: the three states, or the tags in use. */
function FieldColors({
  colorBy,
  tags,
  canTag,
  onAddTag,
}: Pick<Props, "colorBy" | "tags" | "canTag" | "onAddTag">) {
  const { t } = useLocale();
  const [explained, setExplained] = useState(false);
  return (
    <>
      {colorBy === "status" ? (
        <>
          <button
            aria-expanded={explained}
            onClick={() => setExplained((e) => !e)}
            className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-2 pb-1 pt-2 text-left text-slate-200"
          >
            {STATES.map(({ tone, name }) => (
              <span key={name} className="flex items-center gap-1.5">
                <Dot color={TONE_HEX[tone]} />
                {t.states[name]}
              </span>
            ))}
            <ChevronIcon
              className={`ml-auto size-3.5 text-muted transition-transform ${
                explained ? "-rotate-90" : "rotate-90"
              }`}
            />
            <span className="sr-only">{t.legend.more}</span>
          </button>
          {explained && (
            <dl className="rise-in max-w-72 space-y-1.5 px-2 pb-1.5 pt-1">
              {STATES.map(({ tone, name }) => (
                <div key={name} className="flex gap-2">
                  <dt className="pt-1">
                    <Dot color={TONE_HEX[tone]} />
                    <span className="sr-only">{t.states[name]}</span>
                  </dt>
                  <dd className="text-[11px] leading-4 text-slate-300">
                    {t.states[`${name}Why`]}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </>
      ) : (
        <div className="flex max-w-80 flex-wrap items-center gap-x-3 gap-y-1 px-2 pb-1 pt-2 text-slate-200">
          {tags.slice(0, SHOWN_TAGS).map((tag) => (
            <span key={tag.label} className="flex items-center gap-1.5">
              <Dot color={tag.color} />
              {tag.label}
            </span>
          ))}
          {tags.length > SHOWN_TAGS && (
            <span className="text-muted">+{tags.length - SHOWN_TAGS}</span>
          )}
          <span className="flex items-center gap-1.5 text-muted">
            <Dot color={TONE_HEX.unknown} />
            {t.legend.untagged}
          </span>
          {canTag ? (
            <button
              onClick={onAddTag}
              className="-my-1 flex h-7 items-center gap-1 rounded-full border border-dashed border-white/30 px-2.5 font-medium text-white hover:border-white/60"
            >
              <PlusIcon className="size-3" />
              {t.legend.addTag}
            </button>
          ) : (
            <span className="w-full text-[11px] text-muted">
              {t.legend.openToTag}
            </span>
          )}
        </div>
      )}
    </>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      aria-hidden
      className="block size-2.5 shrink-0 rounded-full"
      style={{ background: color }}
    />
  );
}
