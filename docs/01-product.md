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

## Fields, sections and tags

- A **field** is a polygon drawn on the map or imported from GeoJSON/KML. Its area in hectares is
  computed by the backend.
- A field can be split into **sections** (lots): "La Esperanza / Lote 3". A section must lie inside
  its field. Every answer is computed for fields and for sections.
- Any field or section can carry **tags** in `key:value` form: `client:Juan Perez`, `crop:soy`,
  `zone:larroque-north`, or plain labels such as `to-spray-this-week`.
- The **portfolio** shows every field and section at once, sorted by the worst answer and filterable
  by tag. Example: "which `to-spray-this-week` lots have favorable conditions tomorrow from 6 to 10 am?".

## What the product does not claim

- It does not detect a fire the moment it starts. Satellite detections for Argentina reach FIRMS
  hours after the satellite pass. The UI shows both times: "acquired 2 h ago · received 5 min ago".
- Spraying conditions are decision support, not an agronomic recommendation. Thresholds depend on
  the product, nozzle and equipment, so they are configurable per profile.
- An inversion is estimated from weather variables (calm wind, clear sky, night or early morning).
  It is shown as an estimated risk, never as a detection.
- A single pixel is not a fire. Confidence and the list of confirming sensors are always shown.

## Roadmap

| Phase | Scope |
|---|---|
| 0 — Spike | Sample fields near Larroque, FIRMS ingestion, fire events, field risk, spray conditions, portfolio in the CLI and API |
| 1 — Imagery | Sentinel-2 acquisitions, NDVI/NDRE/NDWI/NBR per field, change detection against each field's own baseline, before/after images, map UI |
| 2 — YOLO and GOES | Smoke and fire detection on Sentinel-2 and GOES tiles, dataset tooling, inference in the worker |
| 3 — MVP | Login, alert rules and spray profiles in the UI, email alerts, history, seen/resolved |
| 4 — Risk and deploy | Wind-aware fire risk, historical baselines, AWS deploy, drone photo upload |

## Phase 0 user stories

1. Load fields, sections and tags from a GeoJSON file.
2. Create, list and delete fields and sections through the API; hectares are computed on save.
3. Ingest FIRMS detections for the Larroque region from four sensors, without duplicates.
4. Group detections of the same fire into one fire event and record why each was grouped.
5. For each fire event, compute distance, direction and severity for every field and section within 10 km.
6. Compute spraying conditions for the next 48 h per field, with the result of every rule.
7. Show the portfolio (fire, spray, anomaly placeholder, data quality) in the CLI and API, filterable by tag.
8. Show when each source was last read and whether the read succeeded.
