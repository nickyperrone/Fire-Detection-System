"use client";

import { useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { useAuthConfig, useLogin } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";

import { Turnstile, type TurnstileHandle } from "./Turnstile";

type Props = {
  /** The link the user came back with was used or expired. */
  expired: boolean;
  onClose: () => void;
};

/** Asks for an address and emails a sign-in link (docs/09-accounts-and-alerts.md). */
export function SignInCard({ expired, onClose }: Props) {
  const { t, locale } = useLocale();
  const login = useLogin();
  const config = useAuthConfig();
  const siteKey = config.data?.captcha_site_key ?? null;
  const [email, setEmail] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const check = useRef<TurnstileHandle>(null);
  // With Cloudflare's check set up, the link is asked for once it has passed.
  const ready = config.isSuccess && (!siteKey || captcha !== null);
  const errorCode = login.error instanceof ApiError ? login.error.code : null;

  return (
    <div
      className="fixed inset-0 z-30 flex items-end justify-center bg-black/50 md:items-center"
      onClick={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="sign-in-title"
        onClick={(e) => e.stopPropagation()}
        className="rise-in glass w-full max-w-md space-y-3 rounded-t-3xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] md:rounded-3xl"
      >
        <h2 id="sign-in-title" className="text-lg font-semibold">
          {t.signIn.title}
        </h2>
        {login.isSuccess ? (
          <p className="text-sm text-slate-200">
            {t.signIn.sent(email.trim())}
          </p>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate(
                { email, locale, captcha },
                { onSettled: () => check.current?.reset() },
              );
            }}
          >
            {expired && <p className="text-sm text-bad">{t.signIn.expired}</p>}
            <p className="text-sm text-slate-300">{t.signIn.why}</p>
            <input
              type="email"
              required
              autoFocus
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.signIn.email}
              aria-label={t.signIn.email}
              className="h-11 w-full rounded-xl border border-line bg-surface-2 px-3 outline-none focus:border-accent"
            />
            {siteKey && (
              <Turnstile
                ref={check}
                siteKey={siteKey}
                locale={locale}
                onToken={setCaptcha}
              />
            )}
            <button
              type="submit"
              disabled={login.isPending || !ready}
              className="h-11 w-full rounded-xl bg-accent font-semibold text-slate-950 disabled:opacity-50"
            >
              {login.isPending ? t.signIn.sending : t.signIn.send}
            </button>
            {login.isError && (
              <p className="text-sm text-bad">
                {errorCode === "captcha"
                  ? t.signIn.captchaFailed
                  : errorCode === "too_many"
                    ? t.signIn.tooMany
                    : t.signIn.failed}
              </p>
            )}
          </form>
        )}
        <button onClick={onClose} className="text-sm text-muted">
          {t.signIn.close}
        </button>
      </section>
    </div>
  );
}
