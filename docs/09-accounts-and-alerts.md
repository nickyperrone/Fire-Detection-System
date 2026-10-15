# 09 — Accounts and email alerts

Fields belong to someone, and alerts must reach that person when the app is closed. Both need an
account. Explore mode ([04-frontend](04-frontend.md#explore-mode-no-login)) stays open to anyone.

## Signing in: a link by email

There are no passwords. A contractor signs in from a phone, often once; an emailed link is easier
than a password, and the click proves the address the alerts will go to.

1. `POST /auth/login {email, locale}` emails a one-time link, valid for 15 minutes. The answer is
   the same whether or not the address has an account, so the endpoint does not reveal who uses
   the app.
2. The link opens `GET /auth/callback?token=…`, a small page with an **Entrar** button; opening it
   uses nothing up. Email security scanners open every link in a message, and a link used up on
   opening would be spent before the person clicks. The button posts the token to
   `POST /auth/callback`: the token is used up, the account is created on the first sign-in, and a
   session starts: a cookie `fw_session` (HttpOnly, SameSite=Lax, Secure outside localhost) valid
   for 30 days. The browser lands back on the map. A link already used or expired shows that on the
   page, with the way to ask for another.
3. `GET /auth/me` answers who is signed in (401 otherwise); `POST /auth/logout` ends the session.

- Requests that change something (POST, PUT, PATCH, DELETE) from a page of another site are
  refused (403) by their `Origin` header, so another site cannot sign someone in to its own
  account or act for them.
- The API does not write an access log: links carry their token in the address.
- Link tokens and session ids are 32 random bytes; the database keeps only their SHA-256 hashes, so
  a copy of the database cannot be used to sign in.
- At most 5 links per address per hour (`auth.login_links_per_hour`), so the form cannot be used to
  flood someone's inbox.
- The address is stored lowercased; the language chosen at sign-in is the language of the emails.

### Bots

The sign-in form sends an email, so a bot could use it to flood inboxes or to spend the email
quota. Three limits stand in the way:

- **Cloudflare Turnstile.** The sign-in card shows Cloudflare's check, which most people pass
  without doing anything. `POST /auth/login` takes its token as `captcha` and asks Cloudflare
  whether it is valid before sending anything; without a valid one the answer is 403
  `{"code": "captcha"}`. The keys are `TURNSTILE_SITE_KEY` (public, given to the page by
  `GET /auth/config`) and `TURNSTILE_SECRET_KEY` (only on the server). Without them, as in
  development, there is no check.
- **Per address:** at most 5 links an hour (above).
- **Per network address:** at most 20 sign-in requests an hour from one IP
  (`auth.login_requests_per_ip_hour`); after that, 429 `{"code": "too_many"}`. Behind Cloudflare
  the IP is `CF-Connecting-IP`. An IPv6 address counts by its /64, the block one connection gets,
  so rotating addresses inside it does not help.
- **For the whole app:** at most 200 sign-in emails an hour (`auth.login_emails_per_hour`), however
  many addresses they go to; past it the answer is still 202, so it says nothing.
- A mail server that refuses an address gets the same 202 as one that accepts it.

## What needs an account

| | Signed out | Signed in |
|---|---|---|
| Fires, lightning, fire risk layer, property lines | yes | yes |
| Fields, lots, tags, settings, answers per field | no | their own |
| Browser alerts | no | yes |
| Email alerts | no | yes |

- Every field and tag belongs to the address that drew it (`territory.owner`, `tag.owner`). The API
  answers 401 to field endpoints without a session, and the field tiles are empty.
- Fields loaded without an account (owner `default`, for example by `make seed`) are moved to an
  account with `make claim EMAIL=…`.

## Email alerts

Same rule as browser alerts ([01-product](01-product.md#settings-per-field)): danger near a field
with alerts on, sent when it starts or grows, not while it lasts.

- **Fire:** a field risk event whose severity is above the severity last emailed for it
  (`field_risk_event.notified_severity`): a new fire near the field, or the same fire closer.
- **Lightning:** flashes within `lightning.radius_m` in the last `lightning.window_minutes`, and no
  lightning email for that field in the last `alerts.lightning_quiet_minutes` (60).
- The worker checks after every fire and lightning run. Each user gets **one email per run**
  listing every field with new danger, worst first: what, how far, which direction, which
  satellites, when it was seen, and a link to the field.
- The email says how to stop it: turn off "Alert me of danger nearby" on the field's card.
- Each email sent is recorded in `alert_email` (address, time, fields, dangers, processing
  version). The "already emailed" marks are written only after the email is accepted by the mail
  server, so a failed send is retried on the next run instead of being lost.

## Summaries

Alerts say what just changed; a summary says how the fields are doing, so the contractor can plan
the week and tell clients about their fields.

- **When:** weekly on Monday at 07:00 Argentina time (the default), daily at 07:00, or never. The
  choice is in the account menu (`PATCH /auth/me {summary}`), next to **Send me one now**
  (`POST /auth/me/summary`), which sends the summary at once.
- **What**, for every field and lot of the account, worst first (the same order as the list):
  - looking back over the period (a day or a week): fire days within 10 km and the closest one,
    lightning flashes within 10 km, and rain in the area (the field's 0.5° weather point, so it is
    the area's rain, not a rain gauge);
  - looking ahead: the next spraying window in 48 h, and the fire forecast when it is HIGH or
    VERY_HIGH in the next 3 days.
- A field with nothing to report says so in one line, so the client's field is never missing.
- The worker checks every 15 minutes which accounts are due (`app_user.summary_sent_at`), and marks
  them only after the mail server accepts the email, as with alerts.
- Same language as the alerts, plain text, with a link to each field and to the summary setting.

## Sending

Plain SMTP, so the provider can change without code changes. Settings come from the environment:
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` and
`APP_URL` (the address links point to).

- **Development:** `docker compose up -d mail` starts Mailpit, which catches every email and shows
  it at http://localhost:8025. Nothing leaves the computer, and sign-in links are opened from there.
- **Production: Resend** over SMTP: `smtp.resend.com`, port 587 with STARTTLS, user `resend`,
  password a Resend API key, kept only in `.env`. The sender must be on a domain verified in
  Resend (DNS records it gives); until then its test sender `onboarding@resend.dev` only delivers
  to the Resend account's own address. The free plan sends 100 emails a day, 3,000 a month.
  Any other SMTP service works the same way, without code changes.
