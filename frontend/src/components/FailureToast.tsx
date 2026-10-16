"use client";

import { useEffect, useState } from "react";

import { useLocale } from "@/i18n/LocaleProvider";
import { useFailures } from "@/lib/failures";

const SHOWN_MS = 4500;

/** One friendly line when an action fails and its page has no place to say so. */
export function FailureToast() {
  const { t } = useLocale();
  const failures = useFailures();
  const [hiddenAt, setHiddenAt] = useState(0);

  useEffect(() => {
    if (failures === hiddenAt) return;
    const timer = setTimeout(() => setHiddenAt(failures), SHOWN_MS);
    return () => clearTimeout(timer);
  }, [failures, hiddenAt]);

  if (failures === hiddenAt) return null;
  return (
    <div
      role="status"
      className="pointer-events-none fixed inset-x-0 bottom-24 z-[60] flex justify-center px-4"
    >
      <p className="pointer-events-auto rounded-2xl bg-slate-900/95 px-4 py-2.5 text-sm text-slate-100 shadow-lg ring-1 ring-white/10">
        {t.app.actionFailed}
      </p>
    </div>
  );
}
