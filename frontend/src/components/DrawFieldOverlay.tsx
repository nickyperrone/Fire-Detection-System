"use client";

import { useState } from "react";

import type { Territory } from "@/api/client";
import { useCreateTerritory } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatHectares } from "@/i18n/text";

import type { DrawTool, FieldDrawing } from "./map/useFieldDrawing";

const TOOLS: DrawTool[] = ["trace", "corners"];

type Props = {
  drawing: FieldDrawing;
  fields: Territory[];
  defaultParentId: number | null;
  onDone: (created: Territory | null) => void;
};

/** Full-screen drawing mode: the map, a top bar, the tool switch and one card at the bottom. */
export function DrawFieldOverlay({ drawing, fields, defaultParentId, onDone }: Props) {
  const { t } = useLocale();
  const [parentId, setParentId] = useState<number | null>(defaultParentId);
  const parentName = fields.find((f) => f.id === parentId)?.name;
  const closed = drawing.polygon !== null;
  const hint = drawing.tool === "trace" ? t.draw.traceHint : t.draw.cornersHint;

  return (
    <>
      <div className="pointer-events-none absolute inset-x-3 top-3 z-20 flex flex-col items-center gap-2 pt-[env(safe-area-inset-top)]">
        <div className="glass pointer-events-auto flex h-12 w-full max-w-xl items-center justify-between rounded-2xl px-2">
          <button onClick={() => onDone(null)} className="rounded-xl px-3 py-2 text-sm text-slate-300">
            {t.draw.cancel}
          </button>
          <span className="truncate text-sm font-semibold">
            {parentName ? t.draw.newLot(parentName) : t.draw.newField}
          </span>
          <button
            onClick={drawing.restart}
            disabled={drawing.hectares === 0}
            className="rounded-xl px-3 py-2 text-sm text-accent disabled:text-muted/50"
          >
            {t.draw.startOver}
          </button>
        </div>
        {!closed && (
          <div className="glass pointer-events-auto flex rounded-full p-1" role="radiogroup" aria-label={t.draw.tools}>
            {TOOLS.map((tool) => (
              <button
                key={tool}
                role="radio"
                aria-checked={drawing.tool === tool}
                onClick={() => drawing.setTool(tool)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                  drawing.tool === tool ? "bg-accent text-slate-950" : "text-slate-300"
                }`}
              >
                {t.draw[tool]}
              </button>
            ))}
          </div>
        )}
      </div>

      <section className="glass fixed inset-x-3 bottom-3 z-20 mx-auto max-h-[60dvh] max-w-xl overflow-y-auto rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <p className="text-3xl font-semibold tabular-nums">{formatHectares(t, drawing.hectares)}</p>
        {closed ? (
          <SaveFieldForm
            drawing={drawing}
            fields={fields}
            parentId={parentId}
            onParentChange={setParentId}
            onDone={onDone}
          />
        ) : drawing.tooSmall ? (
          <p className="mt-1 text-sm text-watch">{t.draw.tooSmall}</p>
        ) : (
          <p className="mt-1 text-sm text-slate-300">
            {hint} {t.draw.zoomHint}
          </p>
        )}
      </section>
    </>
  );
}

type FormProps = {
  drawing: FieldDrawing;
  fields: Territory[];
  parentId: number | null;
  onParentChange: (id: number | null) => void;
  onDone: (created: Territory | null) => void;
};

function SaveFieldForm({ drawing, fields, parentId, onParentChange, onDone }: FormProps) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [more, setMore] = useState(parentId !== null);
  const create = useCreateTerritory();
  const inputClass =
    "mt-1 h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-accent";

  return (
    <form
      className="mt-1 space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate(
          {
            name: name.trim(),
            geometry: drawing.polygon as Record<string, unknown>,
            parent_id: parentId,
            tags: tags
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
          },
          { onSuccess: (created) => onDone(created) },
        );
      }}
    >
      <p className="text-sm text-slate-300">{t.draw.adjust}</p>
      <div className="flex gap-2">
        <input
          autoFocus
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t.draw.namePlaceholder}
          aria-label={t.draw.name}
          className={`${inputClass} mt-0 flex-1`}
        />
        <button
          type="submit"
          disabled={create.isPending || !name.trim()}
          className="h-11 rounded-xl bg-accent px-5 font-semibold text-slate-950 disabled:opacity-50"
        >
          {create.isPending ? t.draw.saving : t.draw.save}
        </button>
      </div>
      {more ? (
        <>
          <label className="block text-sm">
            <span className="text-muted">{t.draw.lotOf}</span>
            <select
              value={parentId ?? ""}
              onChange={(e) => onParentChange(e.target.value ? Number(e.target.value) : null)}
              className={inputClass}
            >
              <option value="">{t.draw.ownField}</option>
              {fields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-muted">{t.draw.tags}</span>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="client:Juan Perez, crop:soy"
              className={inputClass}
            />
          </label>
        </>
      ) : (
        <button type="button" onClick={() => setMore(true)} className="text-sm text-accent">
          {t.draw.more}
        </button>
      )}
      {create.error && <p className="text-sm text-critical">{t.draw.saveFailed(create.error.message)}</p>}
    </form>
  );
}
