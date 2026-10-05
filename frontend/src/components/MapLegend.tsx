"use client";

import { useState } from "react";

import { useLocale } from "@/i18n/LocaleProvider";
import { type Tone, TONE_HEX } from "@/lib/status";
import type { ColorBy } from "@/lib/useUrlState";

import { ChevronIcon, PlusIcon } from "./Icons";

type Props = {
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
// Past this many tags the legend says "+N" instead of growing over the map.
const SHOWN_TAGS = 5;

/** What the field colors mean, and the switch between coloring by state and by tag
 * (docs/01-product.md#field-states). */
export function MapLegend({
  colorBy,
  onColorBy,
  tags,
  canTag,
  onAddTag,
}: Props) {
  const { t } = useLocale();
  const [explained, setExplained] = useState(false);

  return (
    <section
      aria-label={t.legend.label}
      className="liquid w-fit max-w-full rounded-2xl p-1.5 text-xs"
    >
      <div
        role="radiogroup"
        aria-label={t.colorBy.label}
        className="flex rounded-full bg-black/25 p-0.5"
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
    </section>
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
