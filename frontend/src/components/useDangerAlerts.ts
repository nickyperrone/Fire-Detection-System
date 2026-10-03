"use client";

import { useEffect, useReducer, useRef, useSyncExternalStore } from "react";

import type { PortfolioEntry } from "@/api/client";
import type { Messages } from "@/i18n/messages";
import { type Danger, dangerGrew, dangerOf } from "@/lib/danger";

import { headline } from "./FieldSummary";

type Permission = NotificationPermission | "unsupported";

function readPermission(): Permission {
  return typeof Notification === "undefined"
    ? "unsupported"
    : Notification.permission;
}

// The browser has no event for permission changes; the hook re-reads it after asking.
const noSubscription = () => () => {};

/** Whether this browser may show alerts, and a way to ask; only a tap may trigger the ask. */
export function useNotificationPermission() {
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const permission = useSyncExternalStore<Permission>(
    noSubscription,
    readPermission,
    () => "unsupported",
  );
  const request = async () => {
    await Notification.requestPermission();
    rerender();
  };
  return { permission, request };
}

/**
 * A browser notification when danger starts or grows near a field with alerts on, while the app
 * is open (docs/01-product.md#settings-per-field). Email alerts come with login.
 */
export function useDangerAlerts(
  entries: PortfolioEntry[] | undefined,
  t: Messages,
) {
  const seen = useRef(new Map<number, Danger>());
  useEffect(() => {
    if (!entries) return;
    for (const entry of entries) {
      const now = dangerOf(entry);
      const grew = dangerGrew(seen.current.get(entry.territory_id), now);
      seen.current.set(entry.territory_id, now);
      if (grew && entry.alerts && readPermission() === "granted") {
        new Notification(entry.name, {
          body: headline(t, entry),
          // One notification per field: a newer one replaces the older.
          tag: `field-${entry.territory_id}`,
        });
      }
    }
  }, [entries, t]);
}
