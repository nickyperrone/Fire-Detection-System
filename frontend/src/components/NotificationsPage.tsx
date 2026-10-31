"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  ApiError,
  type Me,
  type Notifications,
  type SummaryFrequency,
} from "@/api/client";
import {
  useChangeNotifications,
  useChangeSummary,
  useConnectTelegram,
  useDisconnectTelegram,
  useSummaryNow,
} from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import {
  activePreset,
  ALERT_KINDS,
  applyPreset,
  type Available,
  kindOn,
  PRESETS,
} from "@/lib/presets";
import { needsHomeScreen } from "@/lib/push";
import { usePush } from "@/lib/usePush";

import { Breadcrumbs } from "./Breadcrumbs";
import { DeleteAccount } from "./DeleteAccount";
import { CloseIcon } from "./Icons";

type Kind = keyof Notifications;
type Channel = keyof Notifications[Kind];

const FREQUENCIES: SummaryFrequency[] = ["WEEKLY", "DAILY", "OFF"];
// While the bot waits for Start, the page asks the server this often whether it is linked.
const LINK_POLL_MS = 3000;

/** Which kinds of danger the account hears about and through which channels
 * (docs/13-notifications.md#the-notifications-page). */
export function NotificationsPage({
  me,
  onClose,
}: {
  me: Me;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const change = useChangeNotifications();
  const changeSummary = useChangeSummary();
  const summaryNow = useSummaryNow();
  const connected = me.telegram.connected;
  const devices = me.push.devices;
  // The channels this account can use now: mail always, the others once set up.
  const available: Available = {
    email: true,
    telegram: connected,
    push: devices > 0,
  };
  const client = useQueryClient();

  // Fresh on opening: whether Telegram is set up or linked can change while the app is open.
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["me"] });
  }, [client]);

  const set = (kind: Kind, channels: Notifications[Kind]) =>
    change.mutate({ ...me.notifications, [kind]: channels });

  return (
    <div>
      <header className="sticky top-0 z-10 -mx-4 border-b border-white/[0.06] bg-[rgb(17_21_28/0.97)] px-4 pb-3 pt-1 backdrop-blur-xl md:-top-4 md:-mt-4 md:pt-4">
        <div className="flex items-center justify-between gap-3">
          <Breadcrumbs items={[{ label: t.page.root, onClick: onClose }]} />
          <button
            onClick={onClose}
            aria-label={t.detail.close}
            className="grid size-10 shrink-0 place-items-center rounded-full bg-white/[0.07] text-slate-300 hover:bg-white/15 hover:text-white md:size-8"
          >
            <CloseIcon className="size-4" />
          </button>
        </div>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">
          {t.notifications.title}
        </h2>
        <p className="mt-0.5 text-sm text-muted">{t.notifications.intro}</p>
      </header>

      <div className="space-y-6 pt-4">
        <Presets
          current={me.notifications}
          available={available}
          onPick={(next) => change.mutate(next)}
        />

        <TelegramCard me={me} />
        <PushCard me={me} />

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-muted">
            {t.notifications.alertsTitle}
          </h3>
          <div className="mt-2 divide-y divide-white/10 overflow-hidden rounded-2xl bg-white/[0.04]">
            {ALERT_KINDS.map((kind) => {
              const channels = me.notifications[kind];
              const on = kindOn(channels, available);
              return (
                <div key={kind} className="px-3 py-3">
                  <button
                    role="switch"
                    aria-checked={on}
                    onClick={() =>
                      set(
                        kind,
                        on
                          ? { email: false, telegram: false, push: false }
                          : {
                              email: true,
                              telegram: connected,
                              push: devices > 0,
                            },
                      )
                    }
                    className="flex w-full items-center justify-between gap-3 text-left text-sm font-medium text-slate-100"
                  >
                    {t.notifications.kinds[kind]}
                    <Switch on={on} />
                  </button>
                  <p className="mt-0.5 text-xs text-muted">
                    {t.notifications.hints[kind]}
                  </p>
                  {on && (
                    <Channels
                      channels={channels}
                      connected={connected}
                      devices={devices}
                      onChange={(next) => set(kind, next)}
                    />
                  )}
                </div>
              );
            })}
          </div>
          <p className="mt-2 px-1 text-xs text-muted">
            {t.notifications.fieldsNote}
          </p>
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-muted">
            {t.notifications.kinds.summary}
          </h3>
          <div className="mt-2 rounded-2xl bg-white/[0.04] px-3 py-3">
            <p className="text-xs text-muted">
              {t.notifications.hints.summary}
            </p>
            <div
              role="radiogroup"
              aria-label={t.notifications.frequency}
              className="mt-2 flex rounded-full bg-white/10 p-0.5"
            >
              {FREQUENCIES.map((frequency) => (
                <button
                  key={frequency}
                  role="radio"
                  aria-checked={me.summary === frequency}
                  onClick={() => changeSummary.mutate(frequency)}
                  className={`flex-1 rounded-full px-3 py-1 text-xs font-medium ${
                    me.summary === frequency
                      ? "bg-accent text-slate-950"
                      : "text-slate-300"
                  }`}
                >
                  {t.summary.frequency[frequency]}
                </button>
              ))}
            </div>
            {me.summary !== "OFF" && (
              <Channels
                channels={me.notifications.summary}
                connected={connected}
                devices={devices}
                onChange={(next) => set("summary", next)}
              />
            )}
            <button
              onClick={() => summaryNow.mutate()}
              disabled={summaryNow.isPending}
              className="mt-3 block text-sm font-medium text-accent disabled:opacity-50"
            >
              {summaryNow.isPending ? t.summary.sending : t.summary.sendNow}
            </button>
            {summaryNow.isSuccess && (
              <p className="mt-1 text-xs text-slate-300">
                {t.summary.sent(me.email)}
              </p>
            )}
            {summaryNow.error && (
              <p className="mt-1 text-xs text-bad">
                {summaryNow.error instanceof ApiError &&
                summaryNow.error.code === "no_fields"
                  ? t.summary.noFields
                  : t.summary.failed}
              </p>
            )}
          </div>
        </section>

        {(change.isError || changeSummary.isError) && (
          <p className="text-xs text-bad">{t.notifications.failed}</p>
        )}

        <DeleteAccount email={me.email} />
      </div>
    </div>
  );
}

function Switch({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden
      className={`h-5 w-9 shrink-0 rounded-full p-0.5 transition ${on ? "bg-accent" : "bg-white/15"}`}
    >
      <span
        className={`block size-4 rounded-full bg-white transition ${on ? "translate-x-4" : ""}`}
      />
    </span>
  );
}

/** Mail and Telegram as chips that turn on and off; WhatsApp is coming. */
function Channels({
  channels,
  connected,
  devices,
  onChange,
}: {
  channels: Notifications[Kind];
  connected: boolean;
  devices: number;
  onChange: (next: Notifications[Kind]) => void;
}) {
  const { t } = useLocale();
  const chip = (channel: Channel, disabled: boolean) => {
    const on = Boolean(channels[channel]) && !disabled;
    return (
      <button
        key={channel}
        aria-pressed={on}
        disabled={disabled}
        title={
          disabled
            ? channel === "push"
              ? t.notifications.needsPush
              : t.notifications.needsTelegram
            : undefined
        }
        onClick={() => onChange({ ...channels, [channel]: !channels[channel] })}
        className={`rounded-full border px-2.5 py-1 text-xs font-medium transition disabled:opacity-40 ${
          on
            ? "border-accent/60 bg-accent/15 text-accent"
            : "border-white/10 text-slate-300 hover:border-white/25"
        }`}
      >
        {t.notifications.channels[channel]}
      </button>
    );
  };
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="mr-0.5 text-xs text-muted">{t.notifications.by}</span>
      {chip("email", false)}
      {chip("telegram", !connected)}
      {chip("push", devices === 0)}
      <span className="rounded-full border border-dashed border-white/10 px-2.5 py-1 text-xs text-muted">
        {t.notifications.channels.whatsapp} · {t.notifications.soon}
      </span>
    </div>
  );
}

/** How much to hear in one tap: everything, what matters, only urgent, or silence. */
function Presets({
  current,
  available,
  onPick,
}: {
  current: Notifications;
  available: Available;
  onPick: (next: Notifications) => void;
}) {
  const { t } = useLocale();
  const active = activePreset(current, available);
  return (
    <section>
      <h3 className="text-xs font-medium uppercase tracking-wider text-muted">
        {t.notifications.presetsTitle}
      </h3>
      <div
        role="radiogroup"
        aria-label={t.notifications.presetsTitle}
        className="mt-2 grid grid-cols-2 gap-1.5"
      >
        {PRESETS.map((preset) => (
          <button
            key={preset}
            role="radio"
            aria-checked={active === preset}
            onClick={() => onPick(applyPreset(current, preset, available))}
            className={`rounded-xl px-3 py-2 text-sm font-semibold ring-1 transition ${
              active === preset
                ? "bg-accent text-slate-950 ring-accent"
                : "bg-white/[0.04] text-slate-100 ring-white/10 hover:bg-white/[0.08]"
            }`}
          >
            {t.notifications.presets[preset]}
          </button>
        ))}
      </div>
      <p className="mt-2 px-1 text-xs text-muted">
        {active
          ? t.notifications.presetHints[active]
          : t.notifications.presetCustom}
      </p>
    </section>
  );
}

/** Push alerts on this device: on, off, or why it cannot be. */
function PushCard({ me }: { me: Me }) {
  const { t } = useLocale();
  const p = t.notifications.push;
  const push = usePush(me.push.public_key);
  const others = me.push.devices - (push.state === "on" ? 1 : 0);
  const unsupportedText =
    typeof navigator !== "undefined" && needsHomeScreen(navigator.userAgent)
      ? p.iphone
      : p.unsupported;
  return (
    <section className="rounded-2xl bg-white/[0.04] px-3 py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-100">{p.title}</span>
        {push.state === "on" && (
          <span className="flex items-center gap-2 text-xs">
            <span className="flex items-center gap-1.5 text-good">
              <span className="size-1.5 rounded-full bg-good" />
              {p.on}
            </span>
            <span className="text-white/20">·</span>
            <button
              onClick={push.disable}
              disabled={push.busy}
              className="text-muted hover:text-white disabled:opacity-50"
            >
              {p.disable}
            </button>
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-muted">
        {!me.push.available
          ? p.unavailable
          : push.state === "unsupported"
            ? unsupportedText
            : push.state === "denied"
              ? p.denied
              : p.body}
      </p>
      {me.push.available && push.state === "off" && (
        <button
          onClick={push.enable}
          disabled={push.busy}
          className="mt-3 h-10 rounded-xl bg-accent px-4 font-semibold text-slate-950 disabled:opacity-50"
        >
          {push.busy ? p.enabling : p.enable}
        </button>
      )}
      {push.failed && <p className="mt-2 text-xs text-bad">{p.failed}</p>}
      {others > 0 && (
        <p className="mt-2 text-xs text-slate-300">
          {p.others(String(others))}
        </p>
      )}
    </section>
  );
}

function TelegramCard({ me }: { me: Me }) {
  const { t } = useLocale();
  const client = useQueryClient();
  const connect = useConnectTelegram();
  const disconnect = useDisconnectTelegram();
  const waiting = connect.isSuccess && !me.telegram.connected;

  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(
      () => client.invalidateQueries({ queryKey: ["me"] }),
      LINK_POLL_MS,
    );
    return () => window.clearInterval(timer);
  }, [waiting, client]);

  return (
    <section className="rounded-2xl bg-white/[0.04] px-3 py-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-100">
          {t.notifications.telegram}
        </span>
        {me.telegram.connected && (
          <span className="flex items-center gap-2 text-xs">
            <span className="flex items-center gap-1.5 text-good">
              <span className="size-1.5 rounded-full bg-good" />
              {t.notifications.connected}
            </span>
            <span className="text-white/20">·</span>
            <button
              onClick={() => disconnect.mutate()}
              disabled={disconnect.isPending}
              className="text-muted hover:text-white disabled:opacity-50"
            >
              {t.notifications.disconnect}
            </button>
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-muted">
        {me.telegram.available
          ? t.notifications.telegramBody
          : t.notifications.unavailable}
      </p>
      {me.telegram.available && !me.telegram.connected && (
        <div className="mt-3">
          {waiting ? (
            <>
              <a
                href={connect.data.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-10 items-center rounded-xl bg-accent px-4 font-semibold text-slate-950"
              >
                {t.notifications.openTelegram}
              </a>
              <p className="mt-2 text-xs text-slate-300">
                {t.notifications.waiting}
              </p>
            </>
          ) : (
            <button
              onClick={() =>
                connect.mutate(undefined, {
                  // Opened from the reply, so a blocked pop-up still leaves the button above.
                  onSuccess: ({ url }) =>
                    window.open(url, "_blank", "noreferrer"),
                })
              }
              disabled={connect.isPending}
              className="h-10 rounded-xl bg-accent px-4 font-semibold text-slate-950 disabled:opacity-50"
            >
              {connect.isPending
                ? t.notifications.connecting
                : t.notifications.connect}
            </button>
          )}
          {connect.isError && (
            <p className="mt-2 text-xs text-bad">{t.notifications.failed}</p>
          )}
        </div>
      )}
    </section>
  );
}
