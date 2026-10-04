# 01 — Product

## User

A crop-spraying contractor working fields around Larroque, Entre Ríos (Argentina). He sprays many
fields for several clients each week, from the ground and with drones. He does not want a GIS tool.
He wants a short answer per field, and to know when that answer changes.

## Three questions per field

| Question | Answer shown | Main inputs |
|---|---|---|
| Is there a fire near my field? | Possible fire, distance, direction, severity, sources, age | NASA FIRMS (VIIRS, MODIS); GOES later |
| Are spraying conditions favorable? | `FAVORABLE`, `CAUTION` or `UNFAVORABLE`, with the rule that failed | Open-Meteo forecast |
| Is something weird in my field? | Anomaly area, type, size, before/after images | Sentinel-2 and Landsat indices; Sentinel-1 radar |

Every answer also carries a data quality state, because "nothing found" and "could not look" are
different answers:

| State | Meaning |
|---|---|
| `GOOD` | All sources for this answer were read recently and covered the field |
| `PARTIAL` | Some sources failed or part of the field was not covered |
| `STALE` | The last successful read is older than the configured limit |
| `CLOUD_OBSCURED` | Imagery exists but clouds cover too much of the field |
| `NO_DATA` | No successful read yet |

### Weather per field

Spraying conditions say whether to spray; the contractor also wants the weather itself, for every
field being watched, their own or a client's.

- **In the list:** one line per field and lot with the weather now: temperature, wind speed and
  where it comes from, gusts, and rain expected in the next 24 h when there is some
  ("22° · wind from S 12 km/h · gusts 23 · 4 mm in 24 h").
- **On the field card**, a Weather section: now (temperature, humidity, wind, gusts, cloud cover)
  and the next 48 h every 3 hours (temperature, wind and gusts, rain and its probability),
  scrollable sideways.
- Same source and hour as the spray answer (Open-Meteo, the field's point on a 0.02° grid,
  refreshed hourly), so the weather and the spray verdict never disagree. When it is older than
  the spray data quality allows, it is shown gray with its age, never as current.
- Wind direction is where the wind **comes from**, as in any forecast; the spray card already
  says where drift goes.

## Fields, sections and tags

- A **field** is a polygon drawn on the map or imported from GeoJSON/KML. Its area in hectares is
  computed by the backend. Fields must lie in Argentina: the backend checks them against the
  Natural Earth 1:10m boundary (`data/boundaries/argentina.geojson`, public domain) with 1 km of
  tolerance for the generalized rivers and coasts.

### Settings per field

A contractor watches their own fields and their clients' fields, and not all of them matter the same
on a given week. Each field and each lot has three settings, changed from its card:

| Setting | Values | Default | What it changes |
|---|---|---|---|
| Alerts | on, off | on | On: danger near it is announced. Off: its answers are still shown, but nothing is announced. |
| On the map | shown, hidden | shown | Hidden: not drawn on the map and listed at the end, under "Hidden". Hiding a field hides its lots. |
| Priority | high, normal, low | normal | The list orders fields by priority first, then by danger. High-priority fields carry a mark. |

- **Danger** is a fire at any severity band or lightning within its radius. An alert is sent when
  it starts (no fire, then a fire; a fire, then a closer one; no lightning, then lightning), not on
  every refresh while it lasts.
- **Where alerts go:** an email ([09-accounts-and-alerts](09-accounts-and-alerts.md)), and a
  browser notification while the app is open, after the user allows them (asked the first time a
  bell is turned on).
- A lot follows its own settings; a hidden field hides its lots whatever their setting.
- `PATCH /territories/{id}/settings` changes any of the three; the portfolio and the territory list
  return them.

### Tags and colors

Tags group fields the way the contractor talks about them: "casa", "cliente 1", "cliente 2",
`crop:soy`. Each tag has a color.

- A tag gets a color from a fixed palette when it is first seen, and the user can change it from any
  field card (tap the tag's dot). The color belongs to the tag, so every field with it changes.
- The palette has no red and no green: those mean danger and all clear everywhere in the app, and
  a "cliente 1" field must never look like a fire.
- **Color fields by** in the layers menu switches the map between **Status** (red and green, the
  default) and **Tags**. With tags, a field takes the color of its first tag (plain labels such as
  "casa" before `key:value` tags, then alphabetical). A lot takes its field's color, so a client's
  field reads as one piece; only a lot of an untagged field uses its own tags. Untagged fields are
  gray. Fires and lightning keep their colors in both modes.
- The tag chips above the list carry their color dot and work as the legend.
- A field's tags are edited on its card: remove one with its ×, add one by typing (existing tags are
  suggested). `GET /tags` lists the tags with their colors, `PATCH /tags/{id}` changes a color, and
  `PUT /territories/{id}/tags` replaces a field's tags.

## Scope: Argentina

The map can be explored anywhere, but everything the product computes is about Argentina:

- Fields and lots can only be drawn inside Argentina. While drawing, everything outside the
  country is grayed out.
- Fire detections (FIRMS, GOES) and lightning are stored only inside Argentina, with the same 1 km
  tolerance as fields, so a fire on the bank of a border river still counts.
- The forecast grid, the fire history and the static heat sources use Argentine cells only.

When the app opens without a position in the link, the map starts over the whole country and
zooms into Larroque, where the first fields are.
- A field can be split into **sections** (lots): "La Esperanza / Lote 3". A section must lie inside
  its field. Every answer is computed for fields and for sections.
- Any field or section can carry **tags** in `key:value` form: `client:Juan Perez`, `crop:soy`,
  `zone:larroque-north`, or plain labels such as `to-spray-this-week`.
- The **portfolio** shows every field and section at once, sorted by the worst answer and filterable
  by tag. Example: "which `to-spray-this-week` lots have favorable conditions tomorrow from 6 to 10 am?".

## Without a field

Anyone can open the map without an account and see fires in the covered regions as they are
ingested (explore mode). Explore mode sends no notifications. Alerts need a login and at least one field.

## What the product does not claim

- It does not detect a fire the moment it starts. Satellite detections for Argentina reach FIRMS
  hours after the satellite pass. The UI shows both times: "acquired 2 h ago · received 5 min ago".
- Spraying conditions are decision support, not an agronomic recommendation. Thresholds depend on
  the product, nozzle and equipment, so they are configurable per profile.
- An inversion is estimated from weather variables (calm wind, clear sky, night or early morning).
  It is shown as an estimated risk, never as a detection.
- A single pixel is not a fire. Confidence and the list of confirming sensors are always shown.

## Benchmark: FieldData

[FieldData](https://www.fielddata.ag/) is an Argentine farm management product used on about 5,000
farms (its own figure, October 2026). It is the closest product a contractor here would compare
Field Watch with, so it is the benchmark for what a field app should do well.

| | FieldData | Field Watch |
|---|---|---|
| Main input | The team writes to a WhatsApp bot (tasks, supplies, invoices) | Satellites and weather, no typing |
| Fields | Paddocks listed by crop with hectares, on a web map | Drawn on the official property lines, by parcel, or detected from imagery |
| Fire near a field | No | FIRMS and GOES-19, every 5–10 minutes, with distance and direction |
| Spraying conditions | No | Hourly, 48 h, with the rule that failed |
| Fire forecast | No | 1–3 days, calibrated against three baselines |
| Livestock, supplies, finances | Yes | No: out of scope |
| Reports | Weekly WhatsApp summary, Excel export | Email alerts when danger grows |

What Field Watch takes from it:

- **Crop totals by hectares** ("Corn 2,927 ha: Lizzy, Jorge, Santa María") are a quick read of a
  portfolio; the tag chips should show the hectares they cover.
- **A weekly summary** for the owner, by email: fires seen near each field, spray windows used and
  missed.
- **Excel export** of fields, lots, tags and their answers, for the accountant or the client.

What it does not take: WhatsApp as the channel. Alerts and summaries go by email and in the app.

## Roadmap

| Phase | Scope |
|---|---|
| 0 — Spike | Sample fields near Larroque, FIRMS ingestion, fire events, field risk, spray conditions, portfolio in the CLI and API |
| 1 — Imagery and map | Sentinel-2 acquisitions, NDVI/NDRE/NDWI/NBR per field, change detection against each field's own baseline, before/after images; map UI with vector tiles and explore mode ([04-frontend](04-frontend.md)) |
| 2 — Speed, history and forecast | GOES-19 fire detection every 10 min (hours earlier than FIRMS for Argentina) and GOES-19 GLM lightning every 20 s, the main natural cause of fires; fire history per field (detections within 10 km in the last 10 years, from the FIRMS archive); fire forecast per field for 24–72 h ([05-fire-forecast](05-fire-forecast.md)); smoke and fire detection with YOLO on Sentinel-2 and GOES tiles |
| 3 — MVP | Login, alert rules and spray profiles in the UI, email alerts for logged-in users with fields, history, seen/resolved; fire and smoke reports from users with a photo, shown as unconfirmed until a satellite or another user confirms them |
| 4 — Risk and deploy | Fire spread direction and speed from wind, fuel and slope; wind-aware field risk; AWS deploy; drone photo upload |

## Phase 0 user stories

1. Load fields, sections and tags from a GeoJSON file.
2. Create, list and delete fields and sections through the API; hectares are computed on save.
3. Ingest FIRMS detections for the Larroque region from four sensors, without duplicates.
4. Group detections of the same fire into one fire event and record why each was grouped.
5. For each fire event, compute distance, direction and severity for every field and section within 10 km.
6. Compute spraying conditions for the next 48 h per field, with the result of every rule.
7. Show the portfolio (fire, spray, anomaly placeholder, data quality) in the CLI and API, filterable by tag.
8. Show when each source was last read and whether the read succeeded.
