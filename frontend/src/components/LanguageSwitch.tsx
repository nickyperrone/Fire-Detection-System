"use client";

import { useLocale } from "@/i18n/LocaleProvider";
import { LOCALES } from "@/i18n/messages";

export function LanguageSwitch() {
  const { locale, setLocale, t } = useLocale();
  return (
    <div
      role="radiogroup"
      aria-label={t.buttons.language}
      className="glass flex rounded-full p-0.5 text-xs font-semibold"
    >
      {LOCALES.map((option) => (
        <button
          key={option}
          role="radio"
          aria-checked={locale === option}
          onClick={() => setLocale(option)}
          className={`rounded-full px-2.5 py-1 uppercase ${
            locale === option ? "bg-white/15 text-white" : "text-muted"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
