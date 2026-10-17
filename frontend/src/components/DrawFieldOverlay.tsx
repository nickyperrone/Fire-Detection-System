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
import { formatHectares, localDate } from "@/i18n/text";
import { ALL_TOOLS, type EditMode, type Step, stepOf } from "@/lib/drawStep";
import { useSettled } from "@/lib/useSettled";

import { PencilMinusIcon, PencilPlusIcon } from "./Icons";
import type { DrawTool, FieldDrawing } from "./map/useFieldDrawing";

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
    t.draw.saveFailed
  );
}

type Props = {
  drawing: FieldDrawing;
  /** Set when drawing a piece to add to or remove from this field, instead of a new field. */
  editing: Territory | null;
  fields: Territory[];
  /** The field a lot is being drawn in, or null for a new field. */
  lotOf: number | null;
  onDone: (created: Territory | null) => void;
  /** The place search, so the field can be found without leaving drawing. */
  search: React.ReactNode;
};

const TOOL_ICON: Record<DrawTool, string> = {
  parcel: "🗺️",
  detect: "🛰️",
  trace: "✏️",
  corners: "📍",
};
const MODES: { mode: EditMode; icon: string }[] = [
  { mode: "move", icon: "✥" },
  { mode: "add", icon: "＋" },
  { mode: "remove", icon: "－" },
];

/** Drawing mode: the map, a slim bar on top, and one card at the bottom that follows the steps
 * (docs/04-frontend.md#drawing-a-field): mark the field, adjust it, save it. What is not needed
 * yet is not on screen. */
export function DrawFieldOverlay({
  drawing,
  editing,
  fields,
  lotOf,
  onDone,
  search,
}: Props) {
  const { t } = useLocale();
  const [parentId, setParentId] = useState<number | null>(lotOf);
  const lotName = fields.find((f) => f.id === lotOf)?.name;
  const [operation, setOperation] = useState<Operation>("add");
  const step = stepOf({
    hasShape: drawing.polygon !== null,
    editingSaved: editing !== null,
    mode: drawing.mode,
    searching: drawing.searching,
    closeEnough: drawing.closeEnough,
    hasNotice: drawing.notice !== null,
  });
  const toolHint = t.draw.hints[drawing.tool];
  const hint = editing
    ? `${t.edit.hints[operation]} ${toolHint}`
    : drawing.mode !== "move"
      ? `${t.draw.modeHints[drawing.mode]} ${toolHint}`
      : toolHint;
  const title = editing
    ? t.edit.title(editing.name)
    : lotName
      ? t.draw.newLot(lotName)
      : t.draw.newField;
  const sign = editing ? (operation === "add" ? "+" : "−") : "";
  const closed = drawing.polygon !== null;
  const tools = editing && !closed ? ALL_TOOLS : step.tools;

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
          <span className="w-16" aria-hidden />
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
        {step.search && (
          <div className="pointer-events-auto w-full max-w-xl">{search}</div>
        )}
      </div>

      <section className="rise-in glass fixed inset-x-3 bottom-3 z-20 mx-auto max-h-[62dvh] max-w-xl overflow-y-auto rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {step.phase === "choose" && !editing ? (
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">
            {lotName ? t.draw.step1Lot(lotName) : t.draw.step1}
          </p>
        ) : (
          <p className="flex items-baseline gap-2">
            <span className="text-3xl font-semibold tabular-nums">
              {sign}
              {formatHectares(t, drawing.hectares)}
            </span>
            {!editing && (
              <span className="text-xs font-semibold uppercase tracking-wide text-accent">
                {t.draw.step2}
              </span>
            )}
          </p>
        )}

        {step.editBar && <AdjustBar drawing={drawing} className="mt-3" />}

        {tools.length > 0 && (
          <ToolPicker
            drawing={drawing}
            tools={tools}
            className={step.editBar ? "mt-3" : "mt-3"}
          />
        )}

        {closed && editing ? (
          <EditOutlineForm
            drawing={drawing}
            field={editing}
            operation={operation}
            onDone={onDone}
          />
        ) : (
          <>
            <Say
              step={step}
              drawing={drawing}
              hint={step.save ? t.draw.modeHints.move : hint}
            />
            {drawing.note && step.editBar && (
              <p className="mt-2 text-sm text-amber-300">
                {t.draw.notes[drawing.note]}
              </p>
            )}
            {drawing.tool === "corners" &&
              drawing.corners > 0 &&
              (tools.length > 0 || !closed) && (
                <CornerControls drawing={drawing} />
              )}
            {step.save && (
              <SaveFieldForm
                drawing={drawing}
                fields={fields}
                parentId={parentId}
                onParentChange={setParentId}
                onDone={onDone}
              />
            )}
          </>
        )}
      </section>
    </>
  );
}

/** The ways to mark the field (or a zone), each with what it takes, in one grid. */
function ToolPicker({
  drawing,
  tools,
  className = "",
}: {
  drawing: FieldDrawing;
  tools: DrawTool[];
  className?: string;
}) {
  const { t } = useLocale();
  return (
    <div
      className={`grid grid-cols-2 gap-2 ${className}`}
      role="radiogroup"
      aria-label={t.draw.tools}
    >
      {tools.map((tool) => {
        const on = drawing.tool === tool;
        return (
          <button
            key={tool}
            role="radio"
            aria-checked={on}
            onClick={() => drawing.setTool(tool)}
            className={`rounded-2xl px-3 py-2 text-left ring-1 transition ${
              on
                ? "bg-accent text-slate-950 ring-accent"
                : "bg-white/[0.04] text-slate-100 ring-white/10 hover:bg-white/[0.08]"
            }`}
          >
            <span className="block text-sm font-semibold">
              {TOOL_ICON[tool]} {t.draw[tool]}
            </span>
            <span
              className={`block text-xs ${on ? "text-slate-800" : "text-slate-400"}`}
            >
              {t.draw.toolHelp[tool]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** With a shape on the map: move its corners, add a zone, take one out, undo, start over. */
function AdjustBar({
  drawing,
  className = "",
}: {
  drawing: FieldDrawing;
  className?: string;
}) {
  const { t } = useLocale();
  return (
    <div className={className}>
      <div
        className="grid grid-cols-3 gap-1 rounded-2xl bg-white/[0.05] p-1"
        role="radiogroup"
        aria-label={t.draw.adjustBar}
      >
        {MODES.map(({ mode, icon }) => (
          <button
            key={mode}
            role="radio"
            aria-checked={drawing.mode === mode}
            onClick={() => drawing.setMode(mode)}
            className={`rounded-xl px-1 py-2 text-[13px] font-semibold leading-tight ${
              drawing.mode === mode
                ? "bg-accent text-slate-950"
                : "text-slate-200 hover:bg-white/10"
            }`}
          >
            <span aria-hidden className="mr-1">
              {icon}
            </span>
            {t.draw.modes[mode]}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex justify-end gap-4 text-sm">
        <button
          onClick={drawing.undo}
          disabled={!drawing.canUndo}
          className="font-medium text-accent disabled:text-muted/50"
        >
          ↶ {t.draw.undo}
        </button>
        <button onClick={drawing.restart} className="font-medium text-accent">
          {t.draw.startOver}
        </button>
      </div>
    </div>
  );
}

/** The line that says what to do now, what is happening, or what went wrong. */
function Say({
  step,
  drawing,
  hint,
}: {
  step: Step;
  drawing: FieldDrawing;
  hint: string;
}) {
  const { t } = useLocale();
  if (step.say === "searching") {
    return (
      <p className="mt-2 text-sm text-slate-300">
        {drawing.tool === "detect" ? t.draw.detecting : t.draw.searching}
      </p>
    );
  }
  if (step.say === "notice" && drawing.notice) {
    return (
      <p className="mt-2 text-sm text-bad">{t.draw.notices[drawing.notice]}</p>
    );
  }
  if (step.say === "find") {
    return <p className="mt-2 text-sm text-slate-300">{t.draw.findFirst}</p>;
  }
  return (
    <p className="mt-2 text-sm text-slate-300">
      {hint}
      {step.phase === "choose" || step.tools.length > 0
        ? ` ${t.draw.zoomHint}`
        : ""}
    </p>
  );
}

function CornerControls({ drawing }: { drawing: FieldDrawing }) {
  const { t } = useLocale();
  return (
    <div className="mt-3 flex items-center gap-2">
      <span className="mr-auto text-xs text-muted tabular-nums">
        {t.draw.cornersCount(drawing.corners)}
      </span>
      <button
        onClick={drawing.undoCorner}
        className="h-10 rounded-xl px-3 text-sm font-medium text-slate-200 ring-1 ring-white/15 hover:bg-white/10"
      >
        {t.draw.undoCorner}
      </button>
      <button
        onClick={drawing.closeCorners}
        disabled={drawing.corners < 3}
        className="h-10 rounded-xl bg-accent px-4 text-sm font-semibold text-slate-950 disabled:opacity-40"
      >
        {t.draw.closeField}
      </button>
    </div>
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
      {drawing.detected && (
        <p className="text-sm text-slate-300">
          {t.draw.detected(
            drawing.detected.dates,
            localDate(t, drawing.detected.first),
            localDate(t, drawing.detected.last),
          )}
        </p>
      )}
      {drawing.parcel && (
        <p className="text-sm text-slate-300">
          {t.draw.fromParcel(drawing.parcel.partida, drawing.parcel.plano)}
        </p>
      )}
      <div className="flex gap-2">
        <input
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
              placeholder={t.draw.tagsPlaceholder}
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
