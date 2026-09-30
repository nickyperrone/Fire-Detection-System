# 03 — Rules

All values below are defaults in [`config/thresholds.yaml`](../config/thresholds.yaml).

## FIRMS ingestion

- Products read for Argentina: `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `VIIRS_SNPP_NRT`, `MODIS_NRT`.
  FIRMS Landsat detections only cover the US and Canada, so they are not read.
- Each run asks for the last 2 days. Overlapping runs are expected; deduplication makes them harmless.
- `acq_date` + `acq_time` (`HHMM`, UTC) become `acquired_at`. FIRMS sometimes drops the leading
  zeros of `acq_time` (`512` means 05:12).
- Confidence is normalized to `low`, `nominal`, `high`:

| Sensor | Raw value | Normalized |
|---|---|---|
| VIIRS | `l` / `n` / `h` | `low` / `nominal` / `high` |
| MODIS | 0–29 | `low` |
| MODIS | 30–79 | `nominal` |
| MODIS | 80–100 | `high` |

- `brightness` is `bright_ti4` for VIIRS and `brightness` for MODIS (Kelvin). `frp` is in MW.
- A failed product (HTTP error, invalid key, unexpected columns) is recorded as a failed
  `ingestion_run` and the other products still run.

## Fire correlation

Rule `spatiotemporal_v1`, applied to observations without a fire event, oldest first:

1. Candidates are fire events with status `ACTIVE` whose geometry is within `max_distance_m` of
   the observation and whose last detection is within `max_time_gap_hours` (24 h). The distance
   depends on the source of the observation: 1,000 m for FIRMS, 3,000 m for GOES, whose pixels
   are about 2 × 3 km here ([06-goes](06-goes.md)).
2. If there are candidates, the observation joins the nearest one. The event hull, last detection,
   observation count, confirming sensors, maximum confidence and maximum FRP are updated.
3. If there are none, a new fire event starts with this observation.
4. The link stores `{"rule", "distance_m", "time_gap_h", "candidates"}`.
5. Events with no detection for `stale_after_hours` (48 h) become `STALE`.

Two events are not merged when a later observation lies between them. That case is rare at 1 km and
will be handled when regional data shows it.

## Field risk

For each active fire event, every territory (fields and sections) within the widest band gets a field
risk event. Distance is the minimum `geography` distance between the event hull and the territory
polygon, so it is 0 when they intersect.

| Distance | Severity |
|---|---|
| intersects | `CRITICAL` |
| < 2 km | `VERY_HIGH` |
| 2–5 km | `HIGH` |
| 5–10 km | `WATCH` |
| > 10 km | no event |

- Bearing is measured from the territory centroid to the fire event centroid, and is shown as a
  compass direction (`NE`).
- `factors` stores distance, confidence, maximum FRP, sensor count and observation count. In Phase 4
  they feed a score that also uses wind direction toward the field.
- When a fire event changes, its field risk events are recomputed with the current processing
  version. Status `SEEN` and `RESOLVED` are kept unless severity goes up, which resets it to `NEW`.

## Spray conditions

Profile `default`. Each rule returns `PASS`, `CAUTION`, `FAIL` or `UNKNOWN` (missing input), with
the value and the threshold.

| Rule | PASS | CAUTION | FAIL |
|---|---|---|---|
| Wind speed (10 m) | 3–13 km/h | < 3 km/h, or 13–15 km/h | > 15 km/h |
| Wind gusts | < 17 km/h | 17–20 km/h | > 20 km/h |
| Delta T | 2–8 °C | < 2 °C, or 8–10 °C | > 10 °C |
| Air temperature | < 28 °C | 28–30 °C | > 30 °C |
| Rain in the next 2 h | < 0.2 mm and probability < 50 % | probability ≥ 50 % | ≥ 0.2 mm |
| Estimated inversion risk | not flagged | flagged | — |

- Overall status: any `FAIL` → `UNFAVORABLE`; else any `CAUTION` → `CAUTION`; else `FAVORABLE`.
  An `UNKNOWN` rule never counts as `PASS`: the hour is at best `CAUTION` and its data quality is `PARTIAL`.
- Delta T is dry-bulb minus wet-bulb temperature. Wet bulb uses Stull (2011), valid for
  RH 5–99 % and −20 to 50 °C.
- Estimated inversion risk is flagged when wind is below 5 km/h, cloud cover below 30 % and it is
  night (`is_day = 0`) or within 2 h after sunrise. It never makes the status `UNFAVORABLE` alone.
- The wind direction is shown with the side of the field where drift goes (wind from the SW drifts NE).

## Data quality

| Answer | `GOOD` | `PARTIAL` | `STALE` | `NO_DATA` |
|---|---|---|---|---|
| Fire | Every FIRMS product succeeded within 12 h | Some products failed in the last run | Last success older than 12 h | No successful run |
| Spray | Forecast read within 3 h and all rule inputs present | Some inputs missing | Forecast older than 3 h | No forecast |

FIRMS cannot see through thick cloud. Phase 0 cannot tell a cloudy pass from a clear one with no
fire, so the fire answer never says "no fire": it says "no detections".
