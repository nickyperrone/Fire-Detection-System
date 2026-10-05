"use client";

import { useLocale } from "@/i18n/LocaleProvider";

import { ChevronIcon } from "./Icons";

type Crumb = { label: string; onClick?: () => void };

/** Where you are, each step a way back: `Mis campos › La Esperanza › Lote 3`. The last step is
 * the page itself. On a phone the first steps of a long trail shorten to "…". */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useLocale();
  return (
    <nav aria-label={t.page.crumbs} className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1 text-[13px]">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          const shortened = items.length > 2 && i < items.length - 2;
          return (
            <li
              key={`${i}-${item.label}`}
              className={`flex min-w-0 items-center gap-1 ${last ? "" : "shrink-0"}`}
            >
              {last ? (
                <span aria-current="page" className="truncate text-slate-200">
                  {item.label}
                </span>
              ) : (
                <button
                  onClick={item.onClick}
                  className="max-w-40 truncate rounded-md text-muted hover:text-white"
                >
                  {shortened ? (
                    <>
                      <span className="md:hidden" aria-hidden>
                        …
                      </span>
                      <span className="max-md:sr-only">{item.label}</span>
                    </>
                  ) : (
                    item.label
                  )}
                </button>
              )}
              {!last && (
                <ChevronIcon className="size-3 shrink-0 text-white/30" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
