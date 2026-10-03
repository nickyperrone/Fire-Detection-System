"use client";

import type { PortfolioEntry, SettingsIn } from "@/api/client";
import { useChangeSettings, useMe } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

import { BellIcon, BellOffIcon, EyeIcon, EyeOffIcon, StarIcon } from "./Icons";
import { useNotificationPermission } from "./useDangerAlerts";

const PRIORITIES = ["HIGH", "NORMAL", "LOW"] as const;

/** Alerts, visibility and priority of one field or lot (docs/01-product.md#settings-per-field). */
export function FieldSettings({ entry }: { entry: PortfolioEntry }) {
  const { t } = useLocale();
  const change = useChangeSettings();
  const me = useMe();
  const { permission, request } = useNotificationPermission();
  const set = (body: SettingsIn) =>
    change.mutate({ id: entry.territory_id, body });

  return (
    <div className="divide-y divide-white/10 overflow-hidden rounded-2xl bg-white/[0.04]">
      <div>
        <SettingSwitch
          icon={entry.alerts ? <BellIcon /> : <BellOffIcon />}
          label={t.settings.alerts}
          on={entry.alerts}
          onToggle={() => {
            set({ alerts: !entry.alerts });
            if (!entry.alerts && permission === "default") void request();
          }}
        />
        {entry.alerts && me.data && (
          <p className="px-3 pb-2 text-xs text-muted">
            {t.settings.alertsHint(me.data.email)}
          </p>
        )}
        {entry.alerts && permission === "default" && (
          <button
            onClick={() => void request()}
            className="px-3 pb-3 text-sm text-accent"
          >
            {t.settings.allowBrowser}
          </button>
        )}
        {entry.alerts && permission === "denied" && (
          <p className="px-3 pb-3 text-xs text-muted">
            {t.settings.browserBlocked}
          </p>
        )}
      </div>
      <SettingSwitch
        icon={entry.visible ? <EyeIcon /> : <EyeOffIcon />}
        label={t.settings.visible}
        on={entry.visible}
        onToggle={() => set({ visible: !entry.visible })}
      />
      <div className="flex items-center justify-between gap-3 px-3 py-3 text-sm">
        <span className="flex items-center gap-2 text-slate-200">
          <StarIcon className="size-4" />
          {t.settings.priority}
        </span>
        <div
          role="radiogroup"
          aria-label={t.settings.priority}
          className="flex rounded-full bg-white/10 p-0.5"
        >
          {PRIORITIES.map((priority) => (
            <button
              key={priority}
              role="radio"
              aria-checked={entry.priority === priority}
              onClick={() => set({ priority })}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                entry.priority === priority
                  ? "bg-accent text-slate-950"
                  : "text-slate-300"
              }`}
            >
              {t.settings.priorities[priority]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SettingSwitch({
  icon,
  label,
  on,
  onToggle,
}: {
  icon: React.ReactNode;
  label: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left text-sm text-slate-200"
    >
      <span className="flex items-center gap-2 [&_svg]:size-4">
        {icon}
        {label}
      </span>
      <span
        className={`h-5 w-9 shrink-0 rounded-full p-0.5 transition ${on ? "bg-accent" : "bg-white/15"}`}
      >
        <span
          className={`block size-4 rounded-full bg-white transition ${on ? "translate-x-4" : ""}`}
        />
      </span>
    </button>
  );
}
