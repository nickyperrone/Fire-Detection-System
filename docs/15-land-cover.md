# 15 — What is in the field

A fire 6 km away means one thing next to a soybean stubble and another next to a grove with a
house in it. Trees burn longer and spread embers; where there is a house there may be people. So
Field Watch looks at what covers each field and the ground around it, and uses it in the fire
danger and in the alerts.

## Source

**ESA WorldCover 10 m 2021 (v200)**: a land cover map of the whole planet, made by ESA with a
machine-learning classifier on a year of Sentinel-1 radar and Sentinel-2 optical images. It is
free (CC BY 4.0) and published as cloud-optimized GeoTIFFs on a public bucket, one file per 3°
square named after its south-west corner (`S36W060` covers 36°S–33°S, 60°W–57°W). Only the
field's box is read from it, a few hundred kilobytes.

Classes used: trees (10) and shrubs (20) count as **trees**; grassland (30) is **grass**;
cropland (40) is **crops**; built-up (50) is **buildings**; open water (80) and herbaceous wetland
(90) are **water**. The rest shows as "other".

Why not our own model: a detector of trees and houses trained on 10 m imagery would be a worse
copy of this map, which ESA validated across the world. A single farmhouse is one to five pixels;
WorldCover marks most farmsteads with their sheds and yards, and isolated small buildings can be
missed. This is said where it matters: the field page names the source.

## Per field

The worker (`land cover` job, every 10 minutes, on the images thread) reads every territory, field
or lot, that has no land cover yet or whose outline changed since (an md5 of the outline is kept):

- **Shares** of each class inside the outline, adding up to 1.
- **Buildings inside** and **buildings nearby** (in a 300 m ring around the outline,
  `land_cover.ring_m`), in m², from the pixel count and the pixel's ground area at that latitude.

A field that fails to read (network, missing file) is tried again on the next run.

## What it changes

Thresholds in `field_risk.land_cover`.

- **Wooded**: trees and shrubs cover 15 % of the field or more.
- **With buildings**: 300 m² or more of buildings inside the field or in the ring.
- Either one makes every fire near the field **one band worse** (`WATCH` → `HIGH`), added to what
  the wind does ([03-rules](03-rules.md#wind)), never up to `CRITICAL`. Since the fire alerts follow
  the bands ([13-notifications](13-notifications.md)), the owner hears of the fire from farther
  away, which is sooner.
- **With buildings**, an alert of a distant fire also arrives **with sound**, instead of silently.
- The **Telegram alert** says what the field holds: "🏠 Hay construcciones cerca · 🌳 Árboles 22 %
  · 🌾 Cultivo 70 %".
- The risk event's `factors` keep `trees_share`, `built_m2` and `land_raised_by`.

## On screen

The field page has **Qué hay en el campo** under Fire: a bar with the shares (crops, grass, trees,
water, buildings), a line for buildings in or near the field and one for many trees, each saying
what it changes, and the source. A new field says it is being read until the worker has done it.

`GET /territories/{id}/land-cover` returns the shares, the building areas, `wooded` and
`has_buildings`, or `null` while it is pending.
