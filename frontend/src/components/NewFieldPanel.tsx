"use client";

import { useState } from "react";

import type { Territory } from "@/api/client";
import { useCreateTerritory } from "@/api/queries";
import { formatHectares } from "@/lib/format";

import type { FieldDrawing } from "./map/useFieldDrawing";

type Props = {
  drawing: FieldDrawing;
  fields: Territory[];
  defaultParentId: number | null;
  onDone: (created: Territory | null) => void;
};

export function NewFieldPanel({ drawing, fields, defaultParentId, onDone }: Props) {
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [parentId, setParentId] = useState<number | null>(defaultParentId);
  const create = useCreateTerritory();

  if (!drawing.polygon) {
    return (
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Draw a field</h2>
        <p className="text-sm text-slate-300">
          Tap each corner of the field on the map. Tap the first corner again to close it.
        </p>
        <p className="text-3xl font-semibold tabular-nums">{formatHectares(drawing.hectares)}</p>
        <button onClick={() => onDone(null)} className="text-sm text-muted">
          Cancel
        </button>
      </div>
    );
  }

  const save = () =>
    create.mutate(
      {
        name: name.trim(),
        geometry: drawing.polygon as Record<string, unknown>,
        parent_id: parentId,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      },
      { onSuccess: (created) => onDone(created) },
    );

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <h2 className="text-lg font-semibold">New {parentId ? "lot" : "field"} · {formatHectares(drawing.hectares)}</h2>
      <label className="block text-sm">
        <span className="text-muted">Name</span>
        <input
          autoFocus
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="La Esperanza"
          className="mt-1 h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-accent"
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted">Inside field (for a lot)</span>
        <select
          value={parentId ?? ""}
          onChange={(e) => setParentId(e.target.value ? Number(e.target.value) : null)}
          className="mt-1 h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-accent"
        >
          <option value="">None, it is a field</option>
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
          className="mt-1 h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-accent"
        />
      </label>
      {create.error && <p className="text-sm text-critical">{create.error.message}</p>}
      <div className="flex gap-3 pt-1">
        <button
          type="submit"
          disabled={create.isPending || !name.trim()}
          className="h-11 flex-1 rounded-xl bg-accent font-semibold text-slate-950 disabled:opacity-50"
        >
          {create.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={() => onDone(null)} className="h-11 rounded-xl px-4 text-muted">
          Cancel
        </button>
      </div>
    </form>
  );
}
