import type { Tone } from "@/lib/status";

const TONE_CLASSES: Record<Tone, string> = {
  bad: "bg-bad/15 text-bad border-bad/40",
  good: "bg-good/15 text-good border-good/40",
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
