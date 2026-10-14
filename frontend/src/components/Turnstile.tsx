"use client";

import { useEffect, useImperativeHandle, useRef, type Ref } from "react";

const SCRIPT =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type TurnstileApi = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () =>
      window.turnstile ? resolve(window.turnstile) : reject();
    script.onerror = () => {
      loading = null;
      reject();
    };
    document.head.append(script);
  });
  return loading;
}

export type TurnstileHandle = { reset: () => void };

/** Cloudflare's check that a person, not a bot, asks for a sign-in link
 * (docs/09-accounts-and-alerts.md#bots). It stays invisible unless Cloudflare needs a tap. */
export function Turnstile({
  siteKey,
  locale,
  onToken,
  ref,
}: {
  siteKey: string;
  locale: string;
  onToken: (token: string | null) => void;
  ref?: Ref<TurnstileHandle>;
}) {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<string | null>(null);
  const latest = useRef(onToken);
  useEffect(() => {
    latest.current = onToken;
  });

  useImperativeHandle(ref, () => ({
    // A token works once: after each try the check starts again.
    reset: () => {
      latest.current(null);
      if (widget.current) window.turnstile?.reset(widget.current);
    },
  }));

  useEffect(() => {
    let gone = false;
    loadTurnstile()
      .then((api) => {
        if (gone || !box.current) return;
        widget.current = api.render(box.current, {
          sitekey: siteKey,
          theme: "dark",
          language: locale,
          appearance: "interaction-only",
          callback: (token: string) => latest.current(token),
          "expired-callback": () => latest.current(null),
          "error-callback": () => latest.current(null),
        });
      })
      .catch(() => latest.current(null));
    return () => {
      gone = true;
      if (widget.current) window.turnstile?.remove(widget.current);
      widget.current = null;
    };
  }, [siteKey, locale]);

  return <div ref={box} className="flex justify-center empty:hidden" />;
}
