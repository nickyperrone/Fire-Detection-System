"use client";

import { useLocale } from "@/i18n/LocaleProvider";

import { ChevronIcon } from "./Icons";

type Crumb = { label: string; onClick: () => void };

/** The way back from a page, one step per level: `Mis campos › Campo Larroque`. The page's own
 * name is its title, right below, so it is not repeated here. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useLocale();
  return (
    <nav aria-label={t.page.crumbs} className="min-w-0">
      <ol className="flex min-w-0 items-center text-[13px]">
        {items.map((item, i) => (
          <li
            key={`${i}-${item.label}`}
            className={`flex items-center ${i === 0 ? "shrink-0" : "min-w-0"}`}
          >
            {i > 0 && (
              <ChevronIcon className="mx-0.5 size-3 shrink-0 text-white/30" />
            )}
            <button
              onClick={item.onClick}
              className="-my-2 truncate rounded-md px-1 py-2 text-muted hover:text-white"
            >
              {item.label}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
