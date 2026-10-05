"use client";

import { ApiError, type Me, type SummaryFrequency } from "@/api/client";
import { useChangeSummary, useLogout, useSummaryNow } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

const FREQUENCIES: SummaryFrequency[] = ["WEEKLY", "DAILY", "OFF"];

/** The signed-in account: its address, the summary frequency and sign out. */
export function AccountMenu({ me }: { me: Me }) {
  const { t } = useLocale();
  const logout = useLogout();
  const changeSummary = useChangeSummary();
  const summaryNow = useSummaryNow();

  return (
    <div className="text-sm">
      <p className="break-all text-slate-300">{t.signIn.account(me.email)}</p>
      <p className="mt-3 text-xs text-muted">{t.summary.title}</p>
      <div
        role="radiogroup"
        aria-label={t.summary.title}
        className="mt-1 flex rounded-full bg-white/10 p-0.5"
      >
        {FREQUENCIES.map((frequency) => (
          <button
            key={frequency}
            role="radio"
            aria-checked={me.summary === frequency}
            onClick={() => changeSummary.mutate(frequency)}
            className={`flex-1 rounded-full px-3 py-1 text-xs font-medium ${
              me.summary === frequency
                ? "bg-accent text-slate-950"
                : "text-slate-300"
            }`}
          >
            {t.summary.frequency[frequency]}
          </button>
        ))}
      </div>
      <button
        onClick={() => summaryNow.mutate()}
        disabled={summaryNow.isPending}
        className="mt-2 block font-medium text-accent disabled:opacity-50"
      >
        {summaryNow.isPending ? t.summary.sending : t.summary.sendNow}
      </button>
      {summaryNow.isSuccess && (
        <p className="mt-1 text-xs text-slate-300">
          {t.summary.sent(me.email)}
        </p>
      )}
      {summaryNow.error && (
        <p className="mt-1 text-xs text-bad">
          {summaryNow.error instanceof ApiError &&
          summaryNow.error.code === "no_fields"
            ? t.summary.noFields
            : t.summary.failed}
        </p>
      )}
      <button
        onClick={() => logout.mutate()}
        className="mt-3 block font-medium text-accent"
      >
        {t.signIn.signOut}
      </button>
    </div>
  );
}
