# 13 — Notifications: what, how serious, and where

A contractor with many fields does not want every distant fire on the phone, but does want the
fire next to a client's field at once, wherever they are. Each account chooses which kinds of
danger it hears about and through which channel: email, Telegram, push notifications on its
devices, and later WhatsApp. Every alert, in every channel, has a one-tap way to stop that kind
([Unsubscribing](#unsubscribing)).

## Kinds

| Kind | When | Default |
|---|---|---|
| **Fuego alto** | A fire inside the field or within 2 km (`CRITICAL`, `VERY_HIGH`) | on |
| **Fuego medio** | A fire 2 to 5 km away (`HIGH`) | on |
| **Fuego lejano** | A fire 5 to 10 km away (`WATCH`) | off |
| **Rayos** | Lightning within 10 km in the last hour | on |
| **Clima adverso** | In the next 24 h at the field: gusts of 60 km/h or more, or 30 mm of rain or more in a day, or 10 mm or more in an hour | on |
| **Resumen** | The daily or weekly summary ([09](09-accounts-and-alerts.md#summaries)) | weekly, by email |

- The kinds apply to every field of the account whose "Avisarme si hay peligro cerca" is on; a
  field with it off sends nothing, as before.
- A fire is announced when it appears and again only when it moves up a kind (a far fire that
  comes within 2 km is announced again as Fuego alto).
- Clima adverso is announced once per field and episode: again only after
  `alerts.weather_quiet_hours` (12) without it. Its thresholds are in `config/thresholds.yaml`
  (`alerts.weather`), apart from the spraying thresholds: these are about damage and planning, not
  about a spraying window.

## Channels

Each kind has its own channels: email, Telegram and push, each on or off. Telegram only counts once
the account is connected, and push once a device has agreed to it. WhatsApp shows as coming soon until it is set up
([WhatsApp](#whatsapp)).

Defaults: every kind that is on goes to email, Telegram and push (where there is one); the summary
goes by email.

## Push

Notifications on the phone or the computer, which arrive even with Field Watch closed. They use
the standard Web Push (VAPID): free, with no app to install. The server signs each push with its own
key pair, `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` (`python -m app.cli vapid-keys` makes one);
without them push is off and the page says it is not available.

- **Turning it on.** In Notificaciones, "Activar avisos acá" asks the browser for permission (only
  when tapped), subscribes it and sends the server its address and keys (`POST /push/subscribe`).
  An account can have up to 10 devices, each turned on or off on its own page. On an iPhone it
  works only once Field Watch has been added to the Home Screen, and the page says so.
- **The alert** is one notification per field with new danger, in the same words as Telegram's
  ("Posible fuego a 1,9 km al E de Campo Larroque", the wind toward the field and the time it
  would take to arrive, what the field holds). The next one for the same field replaces it and
  rings again. It stays on screen until someone looks at it, except a distant fire alone, which
  arrives without sound like Telegram's. Tapping it opens the field in the app, in the open window
  if there is one.
- **Buttons:** *Abrir*, and *Desuscribirme*, which turns that kind of alert off for push in one
  tap, without opening anything ([Unsubscribing](#unsubscribing)).
- A device that has been uninstalled or cleared answers "gone" and is forgotten on the next alert.
  A push that fails for another reason is not marked as delivered, so the next run tries again.
  A push is kept by the push service for 3 hours at most: an alert that old is worse than none.
- **If this browser gets push, it does not also show the alert of the open tab**, so nobody is told
  twice.

## Unsubscribing

Every alert carries a way out that needs no sign-in and no steps:

- **Email** (alerts and the summary): a line at the end ("Dejar de recibir estos avisos por mail
  con un toque") and the `List-Unsubscribe` headers, so Gmail and others show their own
  "Unsubscribe" button (RFC 8058, one tap).
- **Push:** the notification's *Desuscribirme* button.
- **Telegram:** the alert's *🔕 Silenciar este tipo* button, which turns that kind off in that chat
  and says so.

Each link carries a signature made with a key that belongs to the account, so it cannot be made up
for another account, another kind or another channel. It points to `GET /unsubscribe?t=…`, a page
with a button that changes nothing by itself (a mail scanner opens every link), and `POST` turns
that kind off for that channel and says so, with a link to Notificaciones to change it back. A
mail app's own one-tap and the notification's button do the `POST` directly. What it turns off is
exactly one kind (or "all danger alerts" from an email, which never touches the summary) in one
channel; the other channels and kinds stay as they were.

## Telegram

The official Bot API, free. The bot's token is `TELEGRAM_BOT_TOKEN` in the environment, never in
the repository.

- **Connecting.** "Conectar Telegram" in the notifications page asks the API for a one-time code
  (stored hashed, valid 15 minutes) and opens `https://t.me/<bot>?start=<code>`. Telegram opens the
  bot, the user taps Start, and the bot receives `/start <code>`: the chat is linked to the account
  and the bot answers that alerts will arrive there. The page shows "Conectado" from then on.
- **Disconnecting.** From the page, or `/stop` to the bot.
- **Receiving.** The worker asks Telegram for new messages every few seconds (`getUpdates`), so it
  works without a public address; on a server it can switch to a webhook without other changes.
- **The alert** is one photo message per field with new danger:
  - the caption starts with 🔴 **ALERTA!**, then what and where ("Posible fuego a 3,7 km al NE de
    Campo Larroque"), the wind toward the field when it blows from the fire, and the satellite,
    confidence and times;
  - the photo is the affected area: the field's outline, the fires in red with the distance, the
    lightning, the wind arrow, a scale and north, over the satellite basemap;
  - buttons: **Abrir en el mapa** (the field in the app), **📍 Cómo llegar**, **Ya lo vi**, which
    marks the fire as seen on that field and changes the button to say so, and **Ver el campo**
    ([The bot](#the-bot)). With a local `APP_URL` there is no **Abrir en el mapa**: it would not
    open on a phone, and Telegram refuses it in a button.
- **Summaries** by Telegram are the same text as the email, without a photo, and arrive silently.

### The bot

- **Profile.** The worker sets the bot's commands, description (shown before Start) and short
  description (shown in its profile) on start, in Spanish and in English, through the API: the
  bot is defined in the repository, not by hand in BotFather. Only the name and photo stay in
  BotFather; the photo is `docs/brand/field-watch-bot.png`, the Field Watch logo.
- **Driven by buttons**, under the messages, so they show in every Telegram app without opening a
  keyboard. Each message goes straight to the point with an emoji per line, and every view has
  **ℹ️ Saber más** for the rest, or a link to the page. Nothing has to be typed:
  - Linking the chat answers "✅ ¡Listo, estás conectado!" with what will arrive there and the
    menu: **📋 Mis campos**, **🔔 Mis alertas** and **ℹ️ Saber más** (how it works, and the link
    to the app). Anything typed, or `/ayuda`, brings the same menu.
  - **Mis campos** lists each field: "🌾 name · 5.666 ha", the fire ("✅ Sin fuego cerca" or
    "🔥 Fuego a 3,7 km al NE") and spraying this hour ("✅ Se puede pulverizar", "🟡 Pulverizar con
    cuidado", "⛔ No conviene pulverizar"), with a button per field.
  - A field, in the same message: the fire, spraying with its main reason in plain words ("💧 Aire
    muy húmedo: las gotas quedan flotando") and the next window to spray. **Saber más** adds every
    reason, the weather now (temperature, wind, gusts, rain in the next 24 h) and the areas to
    check; **Ver en el mapa** opens the field in the app.
  - **Mis alertas** shows each kind as a button, ✅ on or ▫️ off for this chat; a tap turns it over
    and the message updates. **Saber más** says what each kind is and links to the page for email.
  - **‹ Menú**, **‹ Mis campos** and **‹ Volver** go back; views change the message in place, so
    moving around does not fill the chat.
- **Commands**, in the menu next to the text box, for whoever prefers them: `/campos`,
  `/alertas`, `/ayuda` (the menu), `/stop`. `/start <code>` links the chat; `/start` alone explains how.
- **Sound.** Fuego lejano and summaries arrive without sound; the rest ring.
- **The alert's buttons**, in two rows: **Abrir en el mapa** (public address only) and
  **📍 Cómo llegar**, which opens the closest fire in Google Maps; then **Ya lo vi** and **Ver el
  campo**, which answers below the photo with the field in detail.
- **While the photo is drawn**, the chat shows "sending photo…".
- **Limits.** When Telegram asks to slow down (HTTP 429), the message waits the time it says and
  is sent once more. When the user blocks the bot or deletes the chat (HTTP 403), the account is
  disconnected, as with `/stop`, instead of failing on every alert.
- Every message sent, by any channel, is recorded in `alert_delivery` (account, channel, time,
  fields, dangers, processing version); the "already announced" marks are written only once a
  channel accepted it, so a failed send is retried on the next run.

## The affected-area image

Made by the worker for each alert, 800 × 600 px:

- The box is the field and every danger in the alert, with a margin; the basemap is the satellite
  photo (Esri World Imagery) at the zoom that fits the box, the same layer as the app's
  "Satélite".
- Drawn on top: the field's outline (and its lots dashed), each fire as a red dot with a halo,
  a dashed line from the field to the closest fire with its distance, lightning as yellow marks,
  the wind arrow, a 1 km (or 5 km) scale and north.
- Esri's imagery needs a license for commercial use (see the README's costs); the basemap is a
  setting, so the dark map can replace it.

## The notifications page

From the account menu, **Notificaciones** opens a page in the panel (`?view=notifications`, with
"Mis campos › Notificaciones" breadcrumbs):

- **At the top, "¿Cuánto querés enterarte?"**: four presets that set every kind at once, in every
  channel the account can use: *Todo*, *Lo importante* (what a new account has: fires within 5 km,
  lightning and adverse weather), *Solo urgentes* (only a fire inside a field or within 2 km) and
  *Silencio*. The one that matches the choices is highlighted; a mix of one's own matches none and
  says so. The summary is left alone.
- **Alerts on this device** (push): on or off for this browser, and how many other devices the
  account has.
- A row per kind with its switch, and under it the channels (Mail, Telegram, Push, WhatsApp coming
  soon) as chips that turn on and off. Fuego lejano and Clima adverso say what they mean in one
  line.
- The summary: frequency (Semanal, Diario, No) and channels.
- Telegram: "Conectar Telegram" or "Conectado · Desconectar".
- `GET /auth/me` returns the preferences; `PATCH /auth/me {notifications}` changes them.

## WhatsApp

Later, through the WhatsApp Business Platform (Meta): it needs a Meta Business account, a phone
number for the bot and a message template approved for alerts, and each alert costs a few cents.
The account would then add its number in this page and confirm it with a code sent by WhatsApp.
