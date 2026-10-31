import type { Notifications } from "../api/client";

type Kind = keyof Notifications;
type Channel = keyof Notifications[Kind];

/** One-tap ways to choose how much to hear, so nobody has to go through every kind and channel
 * (docs/13-notifications.md#the-notifications-page). */
export type Preset = "all" | "important" | "urgent" | "none";
export const PRESETS: Preset[] = ["all", "important", "urgent", "none"];

export const ALERT_KINDS: Kind[] = [
  "fire_high",
  "fire_medium",
  "fire_far",
  "lightning",
  "weather",
];

const KINDS_OF: Record<Preset, Kind[]> = {
  all: ALERT_KINDS,
  // What the account starts with: everything near, not the distant fires.
  important: ["fire_high", "fire_medium", "lightning", "weather"],
  // Only a fire inside the field or within 2 km.
  urgent: ["fire_high"],
  none: [],
};

/** The channels the account can really use now: mail always, Telegram once linked, push once a
 * device agreed. */
export type Available = Record<Channel, boolean>;

const CHANNELS: Channel[] = ["email", "telegram", "push"];

/** The preferences with the preset applied: its kinds on in every usable channel, the others off.
 * A channel not usable yet keeps what it had, and the summary is left alone. */
export function applyPreset(
  current: Notifications,
  preset: Preset,
  available: Available,
): Notifications {
  const next = { ...current };
  for (const kind of ALERT_KINDS) {
    const on = KINDS_OF[preset].includes(kind);
    const channels = { ...current[kind] };
    for (const channel of CHANNELS) {
      if (available[channel]) channels[channel] = on;
    }
    next[kind] = channels;
  }
  return next;
}

/** Whether a kind reaches the account in some usable channel. */
export function kindOn(
  channels: Notifications[Kind],
  available: Available,
): boolean {
  return CHANNELS.some(
    (channel) => available[channel] && Boolean(channels[channel]),
  );
}

/** The preset the current choices match exactly, if any. */
export function activePreset(
  current: Notifications,
  available: Available,
): Preset | null {
  const on = ALERT_KINDS.filter((kind) => kindOn(current[kind], available));
  return (
    PRESETS.find(
      (preset) =>
        KINDS_OF[preset].length === on.length &&
        KINDS_OF[preset].every((kind) => on.includes(kind)),
    ) ?? null
  );
}
