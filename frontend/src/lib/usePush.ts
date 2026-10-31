"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";

import { deviceLabel, pushSupported, urlBase64ToUint8Array } from "./push";

export type PushState =
  | "unsupported" // this browser cannot receive push
  | "denied" // the person blocked notifications for this site
  | "off" // it can, and has not been turned on here
  | "on"; // this browser is subscribed

const WORKER = "/sw.js";

async function registration(): Promise<ServiceWorkerRegistration> {
  await navigator.serviceWorker.register(WORKER);
  return navigator.serviceWorker.ready;
}

export async function detect(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const found = await navigator.serviceWorker.getRegistration(WORKER);
  const subscription = await found?.pushManager.getSubscription();
  return subscription ? "on" : "off";
}

/** Push alerts for this browser: whether they are on, and the way to turn them on and off. The
 * browser asks for permission only when a tap calls `enable`. */
export function usePush(publicKey: string | null) {
  const client = useQueryClient();
  const [state, setState] = useState<PushState>("unsupported");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const read = useCallback(async () => setState(await detect()), []);

  useEffect(() => {
    let current = true;
    void detect().then((next) => current && setState(next));
    return () => {
      current = false;
    };
  }, []);

  const refresh = () => client.invalidateQueries({ queryKey: ["me"] });

  const enable = async () => {
    if (!publicKey || busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return;
      const ready = await registration();
      const subscription =
        (await ready.pushManager.getSubscription()) ??
        (await ready.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        }));
      const { endpoint, keys } = subscription.toJSON();
      await api.pushSubscribe({
        endpoint: endpoint ?? subscription.endpoint,
        p256dh: keys?.p256dh ?? "",
        auth: keys?.auth ?? "",
        label: deviceLabel(navigator.userAgent),
      });
      await refresh();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      await read();
    }
  };

  const disable = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const found = await navigator.serviceWorker.getRegistration(WORKER);
      const subscription = await found?.pushManager.getSubscription();
      if (subscription) {
        await api.pushUnsubscribe(subscription.endpoint);
        await subscription.unsubscribe();
      }
      await refresh();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      await read();
    }
  };

  return { state, busy, failed, enable, disable };
}
