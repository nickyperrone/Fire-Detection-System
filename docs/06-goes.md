# 06 — GOES-19: fire every 10 minutes and lightning

Phase 2. FIRMS publishes passes over Argentina about 3 h after they happen. GOES-19, the
geostationary satellite over the Americas, scans the full disk every 10 minutes and its products
are public minutes later. It is coarser (about 2 km per pixel here) and sees fewer small fires,
so it complements FIRMS rather than replacing it.

## Sources

Both come from NOAA's public bucket `noaa-goes19` on AWS (no key), under
`{product}/{year}/{day of year}/{hour}/`.

| Product | Content | Cadence | Published after | Size |
|---|---|---|---|---|
| `ABI-L2-FDCF` | Fire mask, FRP (MW), fire temperature (K) and area per pixel, full disk | 10 min | ~10 min | ~1.8 MB |
| `GLM-L2-LCFA` | Lightning flashes with position, energy and quality | 20 s | ~40 s | ~0.5 MB |

Each provider keeps a cursor: the last object key it processed, stored on its `ingestion_run`.
A run lists the current and previous hour and processes every newer file in order.

## GOES fire detections

- The file is a 5424 × 5424 grid in the GOES fixed-grid projection (geostationary, satellite at
  -75°). The region's bounding box is converted to grid rows and columns first, and only that
  window is read. Pixel centers are converted to latitude and longitude with the formulas in the
  GOES-R Product User Guide.
- A pixel is a detection when its fire mask code is a fire code:

| Mask codes | Meaning | Confidence |
|---|---|---|
| 10, 30 | good fire pixel | high |
| 11, 31 | saturated fire pixel | high |
| 13, 33 | high probability | high |
| 12, 32 | cloud-contaminated | nominal |
| 14, 34 | medium probability | nominal |
| 15, 35 | low probability | low |

  Codes 30–35 are the same classes after the algorithm's temporal filter. Low-probability pixels
  are dropped by default (`goes.min_confidence: nominal`): they are the main source of false alarms.
- Each detection becomes an `observation` with `source = goes`, `satellite = GOES-19`,
  `sensor = ABI`, `acquired_at` = scan start, and `native_id = {scan start}:{row}:{column}`, which
  is stable, so reprocessing a file adds nothing.

## Correlation across sources

A GOES pixel is about 2 × 3 km over Entre Ríos, so its center can be more than 1 km from the
VIIRS detections of the same fire. The correlation radius is set per source of the new
observation: 1,000 m for FIRMS, 3,000 m for GOES. One fire seen by GOES at 14:20 and by VIIRS at
14:32 is one fire event with both sensors in its list.

## Lightning

- Flashes (not groups or events) inside the region with good quality (`flash_quality_flag = 0`)
  are stored in `lightning_flash`: time of the first event, position, energy (J), area (m²).
- `native_id = {product start}:{flash id}`; flash ids are unique within one file.
- Flashes older than `lightning.keep_days` (7) are deleted by the worker.
- Per field: count of flashes within `lightning.radius_m` (10 km) in the last
  `lightning.window_minutes` (60), and the nearest one. A flash near a field is a reason to watch
  it for fire in the next hours, not a fire.
- Map: a lightning layer with flashes from the last hour.

## Colors

One rule for the whole product: red when something is wrong (a fire near the field, spraying
not recommended or only with caution, lightning nearby), green when everything is fine, gray
when there is no data to say either. How serious it is goes in the text ("Inside", "Very close",
"Caution"), not in extra colors.
