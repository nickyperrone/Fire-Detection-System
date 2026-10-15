# 14 — Deploy: one image on Dokploy

The app runs on a server instead of a laptop: alerts keep arriving when the Mac sleeps, and links in
emails and Telegram open from a phone.

## What runs where

```mermaid
flowchart LR
    U["Browser / phone"] -->|"https, port 3000"| W
    subgraph C["App container (Dockerfile)"]
        W["Web<br/>Next.js :3000"] -->|"/api"| A["API<br/>FastAPI :8000"]
        K["Worker<br/>satellites, alerts, bot"]
    end
    A --> DB[("PostGIS<br/>Dokploy database")]
    K --> DB
    K --> T["Telegram, email"]
```

- **One image** (`Dockerfile` at the root) runs the web, the API and the worker
  (`docker/start.sh`). Only the web is published, on **port 3000**; it forwards `/api` to the API
  inside the container, as in development. If one of the three stops, the container stops and
  Dokploy restarts it.
- **PostGIS** runs apart, as a Dokploy database: its data outlives every deploy of the app.
- On start, the container applies the migrations (`alembic upgrade head`), hands the data volumes
  to the user `fieldwatch` and runs everything as that user, never as root.
- In production (`APP_URL` on https) the API has no `/docs` or `/openapi.json`, writes no access
  log (sign-in links carry their token in the address), and `/health` says whether each source
  works but not its error text, which stays in the log.
- The fire forecast models (`data/models`) are part of the repository, so a new server forecasts
  from the first day.

## Setting it up in Dokploy

1. **Database.** Create → Database → PostgreSQL, with the Docker image `postgis/postgis:16-3.4`.
   Note its internal host, user, password and database name.
2. **Application.** Create → Application → GitHub, this repository, branch `main`.
   Build type **Dockerfile**, file `./Dockerfile`.
3. **Environment** (Application → Environment):

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`, from step 1 |
   | `APP_URL` | The public address, e.g. `https://fieldwatch.nicoleperrone.com` |
   | `FIRMS_MAP_KEY` | The NASA FIRMS key |
   | `SMTP_HOST` `SMTP_PORT` `SMTP_USERNAME` `SMTP_PASSWORD` `SMTP_STARTTLS` `SMTP_FROM` | As in `.env` (Resend) |
   | `TELEGRAM_BOT_TOKEN` | The bot's token |
   | `TURNSTILE_SITE_KEY` `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile, for the sign-in form ([09](09-accounts-and-alerts.md#bots)) |

   With `APP_URL` on `https://`, the sign-in cookie is Secure and Telegram alerts get the
   **Abrir en el mapa** button.
4. **Domain.** Application → Domains: the domain, **container port 3000**, HTTPS on.
5. **Volume.** Application → Advanced → Volumes: a volume mounted at `/app/data/snapshots` keeps
   the fields' photo history across deploys. `/app/data/cache` (Sentinel-2 reads) and
   `/app/data/weather` (clouds and rain frames) are rebuilt by the worker if lost.
6. **Deploy.** The health check asks `/api/health` through the web.

## Moving from the laptop

- **The data** (accounts, fields, tags, fire history, forecasts): dump the local database and
  restore it into the Dokploy one:
  `pg_dump -Fc postgresql://fieldwatch:fieldwatch@localhost:5433/fieldwatch > fieldwatch.dump`, then
  `pg_restore --no-owner -d "$URL_OF_THE_DOKPLOY_DATABASE" fieldwatch.dump`. Or start empty and
  run `python -m app.cli load-history` in the container for the fire history.
- **One worker per bot and database.** Once the server runs, stop the laptop's worker: two workers
  would send every alert twice and take turns answering the bot.
- Each account connects Telegram again only if the database starts empty; a restored database
  keeps the link.
