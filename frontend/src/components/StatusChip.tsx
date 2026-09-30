import type { Tone } from "@/lib/status";

const TONE_CLASSES: Record<Tone, string> = {
  critical: "bg-critical/15 text-critical border-critical/40",
  high: "bg-high/15 text-high border-high/40",
  watch: "bg-watch/15 text-watch border-watch/40",
  ok: "bg-ok/15 text-ok border-ok/40",
  // Dashed: "we could not look", as opposed to a real answer.
  unknown: "bg-unknown/15 text-slate-300 border-dashed border-unknown",
};

const DOT_CLASSES: Record<Tone, string> = {
  critical: "bg-critical",
  high: "bg-high",
  watch: "bg-watch",
  ok: "bg-ok",
  unknown: "bg-unknown",
};

export function StatusChip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${TONE_CLASSES[tone]}`}
    >
      <span className={`size-1.5 rounded-full ${DOT_CLASSES[tone]}`} />
      {children}
    </span>
  );
}
