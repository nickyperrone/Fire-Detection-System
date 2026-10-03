"use client";

import { useState } from "react";

import type { Me } from "@/api/client";
import { useLogout } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

type Props = { me: Me | null; onSignIn: () => void };

/** "Sign in" while signed out; the account's initial, with its address and sign out, after. */
export function AccountButton({ me, onSignIn }: Props) {
  const { t } = useLocale();
  const logout = useLogout();
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
          <button
            onClick={() => logout.mutate()}
            className="mt-2 font-medium text-accent"
          >
            {t.signIn.signOut}
          </button>
        </div>
      )}
    </div>
  );
}
