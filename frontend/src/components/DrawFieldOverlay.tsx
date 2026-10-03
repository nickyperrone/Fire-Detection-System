"use client";

import { useState } from "react";

import { ApiError, type OutlineIn, type Territory } from "@/api/client";
import {
  useCreateTerritory,
  useEditOutline,
  useOutlinePreview,
} from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { formatHectares } from "@/i18n/text";
import { useSettled } from "@/lib/useSettled";

import { PencilMinusIcon, PencilPlusIcon } from "./Icons";
import type { DrawTool, FieldDrawing } from "./map/useFieldDrawing";

const TOOLS: DrawTool[] = ["parcel", "trace", "corners"];

type Operation = OutlineIn["operation"];
const PENCILS: { operation: Operation; Icon: typeof PencilPlusIcon }[] = [
  { operation: "add", Icon: PencilPlusIcon },
  { operation: "remove", Icon: PencilMinusIcon },
];
// How long a dragged point must rest before the server is asked what the edit would give.
const PREVIEW_DELAY_MS = 400;

function errorText(t: Messages, error: Error): string {
  return (
    (error instanceof ApiError && error.code && t.draw.errors[error.code]) ||
    t.draw.saveFailed(error.message)
  );
}

type Props = {
  drawing: FieldDrawing;
  /** Set when drawing a piece to add to or remove from this field, instead of a new field. */
  editing: Territory | null;
  fields: Territory[];
  defaultParentId: number | null;
  onDone: (created: Territory | null) => void;
};

/** Full-screen drawing mode: the map, a top bar, the tool switch and one card at the bottom. */
export function DrawFieldOverlay({
  drawing,
  editing,
  fields,
  defaultParentId,
  onDone,
}: Props) {
  const { t } = useLocale();
  const [parentId, setParentId] = useState<number | null>(defaultParentId);
  const parentName = fields.find((f) => f.id === parentId)?.name;
  const closed = drawing.polygon !== null;
  const [operation, setOperation] = useState<Operation>("add");
  const hint = editing
    ? `${t.edit.hints[operation]} ${t.draw.hints[drawing.tool]}`
    : t.draw.hints[drawing.tool];
  const title = editing
    ? t.edit.title(editing.name)
    : parentName
      ? t.draw.newLot(parentName)
      : t.draw.newField;
  const sign = editing ? (operation === "add" ? "+" : "−") : "";

  return (
    <>
      <div className="pointer-events-none absolute inset-x-3 top-3 z-20 flex flex-col items-center gap-2 pt-[env(safe-area-inset-top)]">
        <div className="glass pointer-events-auto flex h-12 w-full max-w-xl items-center justify-between rounded-2xl px-2">
          <button
            onClick={() => onDone(null)}
            className="rounded-xl px-3 py-2 text-sm text-slate-300"
          >
            {t.draw.cancel}
          </button>
          <span className="truncate text-sm font-semibold">{title}</span>
          <button
            onClick={drawing.restart}
            disabled={drawing.hectares === 0}
            className="rounded-xl px-3 py-2 text-sm text-accent disabled:text-muted/50"
          >
            {t.draw.startOver}
          </button>
        </div>
        {editing && (
          <div
            className="glass pointer-events-auto flex rounded-full p-1"
            role="radiogroup"
            aria-label={t.edit.pencils}
          >
            {PENCILS.map(({ operation: option, Icon }) => (
              <button
                key={option}
                role="radio"
                aria-checked={operation === option}
                onClick={() => setOperation(option)}
                className={`flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium ${
                  operation === option
                    ? "bg-accent text-slate-950"
                    : "text-slate-300"
                }`}
              >
                <Icon className="size-4" />
                {t.edit[option]}
              </button>
            ))}
          </div>
        )}
        {!closed && (
          <div
            className="glass pointer-events-auto flex rounded-full p-1"
            role="radiogroup"
            aria-label={t.draw.tools}
          >
            {TOOLS.map((tool) => (
              <button
                key={tool}
                role="radio"
                aria-checked={drawing.tool === tool}
                onClick={() => drawing.setTool(tool)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                  drawing.tool === tool
                    ? "bg-accent text-slate-950"
                    : "text-slate-300"
                }`}
              >
                {t.draw[tool]}
              </button>
            ))}
          </div>
        )}
      </div>

      <section className="glass fixed inset-x-3 bottom-3 z-20 mx-auto max-h-[60dvh] max-w-xl overflow-y-auto rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <p className="text-3xl font-semibold tabular-nums">
          {sign}
          {formatHectares(t, drawing.hectares)}
        </p>
        {closed && editing ? (
          <EditOutlineForm
            drawing={drawing}
            field={editing}
            operation={operation}
            onDone={onDone}
          />
        ) : closed ? (
          <SaveFieldForm
            drawing={drawing}
            fields={fields}
            parentId={parentId}
            onParentChange={setParentId}
            onDone={onDone}
          />
        ) : drawing.searching ? (
          <p className="mt-1 text-sm text-slate-300">{t.draw.searching}</p>
        ) : drawing.notice ? (
          <p className="mt-1 text-sm text-bad">
            {t.draw.notices[drawing.notice]}
          </p>
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

function SaveFieldForm({
  drawing,
  fields,
  parentId,
  onParentChange,
  onDone,
}: FormProps) {
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
            cadastre: drawing.parcel,
            tags: tags
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
          },
          { onSuccess: (created) => onDone(created) },
        );
      }}
    >
      <FitRow drawing={drawing} />
      <p className="text-sm text-slate-300">
        {drawing.parcel &&
          `${t.draw.fromParcel(drawing.parcel.partida, drawing.parcel.plano)} `}
        {t.draw.adjust}
      </p>
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
              onChange={(e) =>
                onParentChange(e.target.value ? Number(e.target.value) : null)
              }
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
        <button
          type="button"
          onClick={() => setMore(true)}
          className="text-sm text-accent"
        >
          {t.draw.more}
        </button>
      )}
      {create.error && (
        <p className="text-sm text-bad">{errorText(t, create.error)}</p>
      )}
    </form>
  );
}

/** What fitting to the property lines did, and the way back to the drawing as it was made. */
function FitRow({ drawing }: { drawing: FieldDrawing }) {
  const { t } = useLocale();
  if (drawing.fitting) {
    return <p className="text-sm text-slate-300">{t.draw.fitting}</p>;
  }
  if (!drawing.fit) return null;
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-2 px-3 py-2 text-sm">
      <span>
        {drawing.fit.applied
          ? t.draw.fitted[drawing.fit.method](drawing.fit.parcels)
          : t.draw.yourDrawing}
      </span>
      <button
        type="button"
        onClick={drawing.toggleFit}
        className="shrink-0 font-medium text-accent"
      >
        {drawing.fit.applied ? t.draw.useMine : t.draw.fitAgain}
      </button>
    </div>
  );
}

type EditProps = {
  drawing: FieldDrawing;
  field: Territory;
  operation: Operation;
  onDone: (changed: Territory | null) => void;
};

/** The piece is drawn: what the field would become, and saving it. */
function EditOutlineForm({ drawing, field, operation, onDone }: EditProps) {
  const { t } = useLocale();
  const piece = useSettled(drawing.polygon, PREVIEW_DELAY_MS);
  const preview = useOutlinePreview(
    field.id,
    operation,
    piece as Record<string, unknown> | null,
  );
  const save = useEditOutline();
  const error = save.error ?? preview.error;
  const ready =
    preview.data && piece === drawing.polygon && !preview.isFetching;

  return (
    <div className="mt-1 space-y-3">
      <FitRow drawing={drawing} />
      <p className="text-sm text-slate-300">
        {preview.data
          ? t.edit.result(field.name, formatHectares(t, preview.data.hectares))
          : !error && t.edit.checking}{" "}
        {t.draw.adjust}
      </p>
      {error && <p className="text-sm text-bad">{errorText(t, error)}</p>}
      <button
        onClick={() =>
          save.mutate(
            {
              id: field.id,
              body: {
                operation,
                geometry: drawing.polygon as Record<string, unknown>,
                preview: false,
              },
            },
            { onSuccess: (changed) => onDone(changed) },
          )
        }
        disabled={!ready || preview.isError || save.isPending}
        className="h-11 w-full rounded-xl bg-accent px-5 font-semibold text-slate-950 disabled:opacity-50"
      >
        {save.isPending ? t.draw.saving : t.edit.save[operation]}
      </button>
    </div>
  );
}
