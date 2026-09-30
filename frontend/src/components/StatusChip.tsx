import type { Tone } from "@/lib/status";

const TONE_CLASSES: Record<Tone, string> = {
  critical: "bg-critical/15 text-critical border-critical/40",
  high: "bg-high/15 text-high border-high/40",
  watch: "bg-watch/15 text-watch border-watch/40",
  ok: "bg-ok/15 text-ok border-ok/40",
  // Dashed: "we could not look", as opposed to a real answer.
  unknown: "bg-unknown/15 text-slate-300 border-dashed border-unknown",
};

type Props = { tone: Tone; icon?: React.ReactNode; children: React.ReactNode };

export function StatusChip({ tone, icon, children }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${TONE_CLASSES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}
