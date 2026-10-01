# 07 — Fire history per field

Phase 2. How often there has been fire near a field in the last 10 years, in which months, and how
close it came. It answers "is this a field that burns around?" and is the label history the fire
forecast ([05-fire-forecast](05-fire-forecast.md)) trains on.

## Source

FIRMS publishes one CSV per country and year with the standard-processing detections:
`https://firms.modaps.eosdis.nasa.gov/data/country/{product}/{year}/{product}_{year}_Argentina.csv`.

- Product: `viirs-snpp` only. One sensor for the whole period keeps years comparable; S-NPP
  covers 2012 onwards. Default years: 2015–2024 (2025 is not published yet).
- Size: about 14 MB per year for Argentina. Files are cached in `data/cache/firms-archive/`
  (not committed) and only downloaded once.
- The `type` column says what the detection is: 0 vegetation fire, 1 volcano, 2 static land
  source (industry, gas flares), 3 offshore. Only type 0 is kept; the others would be false fires.
- Only detections inside the region bounding box are stored: about 20,000 a year for Entre Ríos
  and the Delta (2023), against 165,000 for the whole country.

## Storage

Table `historical_detection`: acquisition time, point, confidence, FRP, day/night, product and
`dedup_key` (same rule as live observations), unique. Loading a year twice adds nothing. It is
separate from `observation` on purpose: history must not create fire events or alerts.

## Per field

Within `history.radius_m` (10 km) of the field, per field and lot:

| Measure | Why |
|---|---|
| Fire days per year | One fire gives many detections; a day with at least one detection is the honest unit |
| Fire days per month, all years together | Which months burn around this field |
| Days with a detection inside the field | Whether the field itself has burned |
| Nearest detection: date and distance | How close it has come |
| Most recent detection: date and distance | Whether it is old history |

Distances are to the field's edge (0 inside), like live field risk.

## In the product

A "Fire history" section in the field detail: one sentence ("In 10 years: fire within 10 km on
34 days; most in August and September; the closest 1.2 km away, 12 Aug 2020"), fire days per year
as small bars, and the twelve months as a strip. Red is used because a fire nearby is bad; a year
with no fire is an empty bar, not green.

## Commands

`make history` downloads the configured years (once) and loads the region. The worker does not
run it: the archive changes once a year.
