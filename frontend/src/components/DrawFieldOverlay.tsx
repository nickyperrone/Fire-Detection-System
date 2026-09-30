"use client";

import { useState } from "react";

import type { Territory } from "@/api/client";
import { useCreateTerritory } from "@/api/queries";
import { formatHectares } from "@/lib/format";

import type { DrawTool, FieldDrawing } from "./map/useFieldDrawing";

const TOOLS: { tool: DrawTool; label: string; hint: string }[] = [
  {
    tool: "trace",
    label: "Trace",
    hint: "Press on the edge of the field and drag your finger around it. Lift to close.",
  },
  {
    tool: "corners",
    label: "Corners",
    hint: "Tap each corner. Tap the first corner again to close.",
  },
];

type Props = {
  drawing: FieldDrawing;
  fields: Territory[];
  defaultParentId: number | null;
  onDone: (created: Territory | null) => void;
};

/** Full-screen drawing mode: the map, a top bar, the tool switch and one card at the bottom. */
export function DrawFieldOverlay({ drawing, fields, defaultParentId, onDone }: Props) {
  const [parentId, setParentId] = useState<number | null>(defaultParentId);
  const parentName = fields.find((f) => f.id === parentId)?.name;
  const closed = drawing.polygon !== null;

  return (
    <>
      <div className="pointer-events-none absolute inset-x-3 top-3 z-20 flex flex-col items-center gap-2 pt-[env(safe-area-inset-top)]">
        <div className="glass pointer-events-auto flex h-12 w-full max-w-xl items-center justify-between rounded-2xl px-2">
          <button onClick={() => onDone(null)} className="rounded-xl px-3 py-2 text-sm text-slate-300">
            Cancel
          </button>
          <span className="truncate text-sm font-semibold">
            {parentName ? `New lot in ${parentName}` : "New field"}
          </span>
          <button
            onClick={drawing.restart}
            disabled={drawing.hectares === 0}
            className="rounded-xl px-3 py-2 text-sm text-accent disabled:text-muted/50"
          >
            Start over
          </button>
        </div>
        {!closed && (
          <div className="glass pointer-events-auto flex rounded-full p-1" role="radiogroup" aria-label="Drawing tool">
            {TOOLS.map(({ tool, label }) => (
              <button
                key={tool}
                role="radio"
                aria-checked={drawing.tool === tool}
                onClick={() => drawing.setTool(tool)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                  drawing.tool === tool ? "bg-accent text-slate-950" : "text-slate-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      <section className="glass fixed inset-x-3 bottom-3 z-20 mx-auto max-h-[60dvh] max-w-xl overflow-y-auto rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <p className="text-3xl font-semibold tabular-nums">{formatHectares(drawing.hectares)}</p>
        {closed ? (
          <SaveFieldForm
            key="form"
            drawing={drawing}
            fields={fields}
            parentId={parentId}
            onParentChange={setParentId}
            onDone={onDone}
          />
        ) : drawing.notice ? (
          <p className="mt-1 text-sm text-watch">{drawing.notice}</p>
        ) : (
          <p className="mt-1 text-sm text-slate-300">
            {TOOLS.find((t) => t.tool === drawing.tool)?.hint} Zoom with two fingers or the wheel.
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
            tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          },
          { onSuccess: (created) => onDone(created) },
        );
      }}
    >
      <p className="text-sm text-slate-300">Drag the points on the map to fit the edge exactly.</p>
      <div className="flex gap-2">
        <input
          autoFocus
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name, e.g. La Esperanza"
          aria-label="Name"
          className={`${inputClass} mt-0 flex-1`}
        />
        <button
          type="submit"
          disabled={create.isPending || !name.trim()}
          className="h-11 rounded-xl bg-accent px-5 font-semibold text-slate-950 disabled:opacity-50"
        >
          {create.isPending ? "Saving…" : "Save"}
        </button>
      </div>
      {more ? (
        <>
          <label className="block text-sm">
            <span className="text-muted">Lot of an existing field</span>
            <select
              value={parentId ?? ""}
              onChange={(e) => onParentChange(e.target.value ? Number(e.target.value) : null)}
              className={inputClass}
            >
              <option value="">No, it is a field of its own</option>
              {fields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-muted">Tags, separated by commas</span>
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
          Make it a lot or add tags
        </button>
      )}
      {create.error && <p className="text-sm text-critical">{create.error.message}</p>}
    </form>
  );
}
