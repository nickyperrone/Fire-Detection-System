# Field Watch

[![CI](https://github.com/nickyperrone/Fire-Detection-System/actions/workflows/ci.yml/badge.svg)](https://github.com/nickyperrone/Fire-Detection-System/actions/workflows/ci.yml)

Satellite monitoring for the fields of a crop-spraying contractor around Larroque, Entre Ríos
(Argentina). For every field and section it answers three questions: is there a fire nearby, are
spraying conditions favorable, and is something unusual happening in the field. Every answer shows
its sources, their timestamps and whether the field could actually be observed.

- **Status:** Phase 1 in progress. Fire and spray answers work in the map, the API and the CLI.
  Field anomalies from Sentinel-2 are next. See the [roadmap](docs/01-product.md#roadmap).
- Built by [Nicole Perrone](https://www.linkedin.com/in/perronenicole/).

## Run it locally

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 or later, and make.

```bash
git clone https://github.com/nickyperrone/Fire-Detection-System.git
cd Fire-Detection-System
cp .env.example .env      # then set FIRMS_MAP_KEY
make setup                # installs dependencies, starts PostGIS, runs migrations
make seed                 # loads the sample fields, sections and tags near Larroque
make run-once             # reads FIRMS and Open-Meteo once and derives everything
make api                  # API on http://localhost:8000
make web                  # in a second terminal: the map on http://localhost:3000
```

- `FIRMS_MAP_KEY` is free: request it at https://firms.modaps.eosdis.nasa.gov/api/map_key/. Without
  it the fire answer shows `NO_DATA` and the spray answer still works (Open-Meteo needs no key).
- `make portfolio` prints every field and section with its answers in the terminal;
  `make portfolio TAG=crop:soy` filters by tag.
- Next.js forwards `/api` to the API, so there is nothing else to configure.
- API docs are at http://localhost:8000/docs. `make worker` runs the scheduled worker (FIRMS
  every 5 min, weather every 60 min).
- `docker compose up --build` runs the database, API and worker together.
- The `postgis/postgis` image is amd64 only. On Apple Silicon Docker runs it under emulation, which
  works but makes the first start take about a minute.
- Real fields go in `data/aoi/private/`, which is not committed: field outlines are private data.

Other commands: `make test` (backend tests), `make web-check` (frontend types, lint and tests),
`make codegen` (regenerate the frontend API types), `make lint`, `make migration m="..."`.

## Example output

`make portfolio TAG=to-spray-this-week`, with a fire detected east of La Esperanza:

```
Campo Norte (311 ha)    client:Maria Gomez  crop:wheat  to-spray-this-week  zone:larroque-nw
  Fire   WATCH       Possible fire 8.7 km E · VIIRS NOAA-21, MODIS Aqua · high · acquired 4 h ago, received 12 min ago
  Spray  UNFAVORABLE gusts 23 km/h > 20 · drift toward N · next favorable Wed 01:00–02:00
  Weird  NO_DATA     vegetation and water change detection is not available yet
La Esperanza / Lote 1 - Soy (194 ha)    crop:soy  to-spray-this-week
  Fire   HIGH        Possible fire 3.9 km NE · VIIRS NOAA-21, MODIS Aqua · high · acquired 4 h ago, received 12 min ago
  Spray  CAUTION     gusts 18 km/h (caution from 17) · drift toward N · next favorable Wed 01:00–02:00
  Weird  NO_DATA     vegetation and water change detection is not available yet
```

Without a FIRMS key the fire line says `NO_DATA  no fire data: FIRMS has not been read successfully`,
never "no detections".

## Architecture

```mermaid
flowchart LR
    FIRMS["NASA FIRMS<br/>VIIRS + MODIS"] --> P["providers/<br/>normalize"]
    METEO["Open-Meteo"] --> P
    P --> I["ingestion<br/>idempotent"] --> C["correlation<br/>observations → fire events"] --> R["field risk<br/>fire event × territory"]
    P --> S["spray conditions<br/>territory × hour"]
    I & C & R & S --> DB[("PostgreSQL + PostGIS")]
    DB --> API["FastAPI"]
    DB --> CLI["CLI portfolio"]
```

- **One read per region, not per field.** FIRMS is queried once per sensor for the Entre Ríos and
  Delta bounding box, and PostGIS matches detections to fields. The number of external calls does
  not grow with the number of fields.
- **Observation, fire event and field risk event are separate.** Three satellites seeing the same fire
  are three observations and one fire event. One fire near fifteen fields is one fire event and
  fifteen field risk events.
- **Idempotent ingestion.** A deterministic key per detection makes reprocessing harmless. The raw
  provider row is kept for traceability.
- **Two timestamps.** `acquired_at` (satellite pass) and `ingested_at` (when we received it). FIRMS
  data for Argentina arrives hours after the pass, and the UI says so.
- **Data quality on every answer:** `GOOD`, `PARTIAL`, `STALE`, `CLOUD_OBSCURED`, `NO_DATA`. "No
  detections" is only shown when the sources were read.
- **Processing version on every derived row.** It combines the package version and a hash of
  `config/thresholds.yaml`, so each historical alert can be traced to the rules that produced it.
- **Thresholds in config.** Correlation radius, severity bands and spray rules live in
  [`config/thresholds.yaml`](config/thresholds.yaml).

Full diagrams, the data model and the decision log are in [02-architecture](docs/02-architecture.md).

## How it is built: spec first

| Spec | Covers |
|---|---|
| [00-conventions](docs/00-conventions.md) | Code and writing rules, commits |
| [01-product](docs/01-product.md) | User, the three questions, fields, sections, tags, roadmap |
| [02-architecture](docs/02-architecture.md) | Pipeline, data model, processing version, stack, decisions |
| [03-rules](docs/03-rules.md) | FIRMS normalization, correlation, severity, spray rules, data quality |
| [04-frontend](docs/04-frontend.md) | Map-first UI, bottom sheet, vector tiles by zoom, explore mode |
| [05-fire-forecast](docs/05-fire-forecast.md) | Fire probability per field for 24–72 h: data, model, evaluation |
| [06-goes](docs/06-goes.md) | GOES-19 fire every 10 minutes, lightning, colors |

CI runs on every push: ruff, the banned-words check, `alembic check` (migrations match the models),
the tests against a PostGIS service container, and a Docker image build.

## Data sources

| Purpose | Source | Phase |
|---|---|---|
| Active fire detections | [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) (VIIRS NOAA-20, NOAA-21, S-NPP; MODIS) | 0 |
| Weather and 48 h forecast | [Open-Meteo](https://open-meteo.com/) | 0 |
| Field imagery, 10 m | Sentinel-2 L2A from the Earth Search STAC catalog | 1 |
| Field imagery, 30 m, thermal | Landsat 8/9 Collection 2 Level-2 | 1 |
| Radar through clouds, flooding | Sentinel-1 GRD | 3 |
| Fire and smoke every 10 min | GOES-19 ABI | 2 |

## Folders

| Folder | Contents |
|---|---|
| `docs/` | Specs |
| `config/` | `thresholds.yaml`: every rule parameter |
| `data/aoi/` | Sample fields, sections and tags near Larroque (GeoJSON) |
| `backend/app/providers/` | FIRMS and Open-Meteo clients that return normalized records |
| `backend/app/services/` | Ingestion, correlation, field risk, spray conditions, data quality, portfolio |
| `backend/app/routers/` | FastAPI endpoints (HTTP only), including vector tiles |
| `backend/alembic/` | Database migrations |
| `backend/tests/` | Unit tests and PostGIS integration tests |
| `frontend/src/components/` | Map, bottom sheet, portfolio, field detail, drawing |
| `frontend/src/api/` | API client, TanStack Query hooks, generated types |
| `.github/workflows/` | CI |
