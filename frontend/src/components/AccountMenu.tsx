"use client";

import type { Me } from "@/api/client";
import { useLogout } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

import { ChevronIcon } from "./Icons";

/** The signed-in account: its address, its notifications and sign out. */
export function AccountMenu({
  me,
  onNotifications,
}: {
  me: Me;
  onNotifications: () => void;
}) {
  const { t } = useLocale();
  const logout = useLogout();

  return (
    <div className="text-sm">
      <p className="break-all text-slate-300">{t.signIn.account(me.email)}</p>
      <button
        onClick={onNotifications}
        className="mt-3 flex w-full items-center justify-between rounded-xl bg-white/[0.07] px-3 py-2 font-medium text-slate-100 hover:bg-white/15"
      >
        {t.notifications.open}
        <ChevronIcon className="size-3.5 text-muted" />
      </button>
      <button
        onClick={() => logout.mutate()}
        className="mt-3 block font-medium text-accent"
      >
        {t.signIn.signOut}
      </button>
    </div>
  );
}
