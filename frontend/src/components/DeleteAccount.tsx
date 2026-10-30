"use client";

import { useState } from "react";

import { ApiError } from "@/api/client";
import { useAccount, useDeleteAccount } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatNumber } from "@/i18n/text";

/** The last thing on the notifications page: closing the account, said plainly first and asked
 * twice (docs/09-accounts-and-alerts.md#closing-an-account). */
export function DeleteAccount({ email }: { email: string }) {
  const { t } = useLocale();
  const d = t.deleteAccount;
  const [asking, setAsking] = useState(false);
  const [typed, setTyped] = useState("");
  const account = useAccount(asking);
  const remove = useDeleteAccount();
  const matches = typed.trim().toLowerCase() === email;

  if (!asking) {
    return (
      <section className="border-t border-white/10 pt-4">
        <button
          onClick={() => setAsking(true)}
          className="text-sm font-medium text-bad"
        >
          {d.open}
        </button>
      </section>
    );
  }
  return (
    <section className="space-y-3 rounded-2xl border border-bad/40 bg-bad/10 p-3.5">
      <h2 className="text-sm font-semibold text-slate-100">{d.title}</h2>
      <p className="text-sm text-slate-200">
        {account.data
          ? d.intro(
              formatNumber(t, account.data.fields),
              formatNumber(t, account.data.lots),
            )
          : d.introShort}
      </p>
      {account.data?.telegram && (
        <p className="text-xs text-slate-300">{d.telegram}</p>
      )}
      <label className="block text-sm">
        <span className="text-slate-300">{d.type(email)}</span>
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          className="mt-1 h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-bad"
        />
      </label>
      {remove.isError && (
        <p className="text-sm text-bad">
          {remove.error instanceof ApiError && remove.error.code === "confirm"
            ? d.mismatch
            : d.failed}
        </p>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => {
            setAsking(false);
            setTyped("");
          }}
          className="h-11 flex-1 rounded-xl text-sm font-medium text-slate-200 ring-1 ring-white/15 hover:bg-white/10"
        >
          {d.cancel}
        </button>
        <button
          onClick={() =>
            remove.mutate(typed, {
              onSuccess: () => window.location.assign("/"),
            })
          }
          disabled={!matches || remove.isPending}
          className="h-11 flex-1 rounded-xl bg-bad text-sm font-semibold text-white disabled:opacity-40"
        >
          {remove.isPending ? d.deleting : d.confirm}
        </button>
      </div>
    </section>
  );
}
