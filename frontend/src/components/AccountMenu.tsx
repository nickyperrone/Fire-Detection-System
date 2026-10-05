"use client";

import { useState } from "react";

import { ApiError, type Me, type SummaryFrequency } from "@/api/client";
import { useChangeSummary, useLogout, useSummaryNow } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

type Props = { me: Me | null; onSignIn: () => void };

const FREQUENCIES: SummaryFrequency[] = ["WEEKLY", "DAILY", "OFF"];

/** "Sign in" while signed out; the account's initial, with its address and sign out, after. */
export function AccountButton({ me, onSignIn }: Props) {
  const { t } = useLocale();
  const logout = useLogout();
  const changeSummary = useChangeSummary();
  const summaryNow = useSummaryNow();
  const [open, setOpen] = useState(false);

  if (!me) {
    return (
      <button
        onClick={onSignIn}
        className="glass whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold text-accent"
      >
        {t.signIn.button}
      </button>
    );
  }
  return (
    <div className="relative">
      <button
        aria-label={t.signIn.account(me.email)}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="glass grid size-7 place-items-center rounded-full text-xs font-semibold uppercase"
      >
        {me.email[0]}
      </button>
      {open && (
        <div className="glass absolute right-0 top-9 z-20 w-max max-w-[80vw] rounded-2xl p-3 text-sm">
          <p className="break-all text-slate-300">
            {t.signIn.account(me.email)}
          </p>
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
      )}
    </div>
  );
}
