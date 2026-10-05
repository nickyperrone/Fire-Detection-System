# 11 — Something unusual in the field

The third question ([01-product](01-product.md#three-questions-per-field)): is part of the field
doing something the rest is not? A patch that dried out, standing water after rain, a burnt
corner. The contractor cannot walk every field of every client every week; a satellite passes
every five days.

## The problem with "change"

A field changes all year on purpose: it is sown, grows green, ripens and is harvested. Compared
with itself a month ago, a harvest looks like a disaster and a sowing like a miracle. So the
question is not "did the field change" but "did one part change differently from the rest".

## Method

For each management unit (each lot, and each field without lots: lots are sown and harvested
apart, so one lot being harvested is not unusual for its field), from Sentinel-2 L2A at 10 m (Earth Search STAC, the same free Copernicus data as
[10-field-detection](10-field-detection.md)):

1. **Scenes.** Every scene of the last 90 days whose scene classification shows at most 20 % of
   the field under cloud or shadow. Only the field's box is read from each image.
2. **Indices per pixel and date.** NDVI (red, near infrared): how green. NDWI (green, near
   infrared): water. NBR (near infrared, shortwave infrared 2.2 µm): burn scars.
3. **Relative to the rest of the field.** For each date, each pixel's index minus the field's
   median that day. A harvest moves the whole field, the median moves with it, and the difference
   stays the same.
4. **Against the pixel's usual difference.** The mean and standard deviation of that difference
   over the earlier dates (at least 3) are the pixel's baseline. On the latest date:
   - **Less green:** NDVI difference at least 2.5 standard deviations and 0.12 below the
     baseline.
   - **Water:** NDWI above 0 (open water) where the baseline was dry.
   - **Burnt:** NBR difference at least 0.25 below the baseline, **and** a satellite fire
     detection within 1 km of the patch between the two clear dates. Freshly tilled or
     sprayed-off ground darkens NBR the same way, so without a detected fire it is not reported
     (if the ground also lost green, the less-green patch reports it). A confirmed burn replaces
     the less-green patch over the same ground.
5. **Patches.** Pixels flagged for the same reason are joined into connected patches; patches
   under 1 ha (100 pixels) are dropped, so single noisy pixels and field edges never count.
6. **Answer.** Each patch has its kind, area, where it lies in the field (N, SE, center…), the
   date, and a score (how far below the baseline). The field's answer is the patches of the
   latest clear date.

Thresholds are in `config/thresholds.yaml` (`anomalies`).

## Data quality

| State | When |
|---|---|
| `GOOD` | The latest clear date is less than 10 days old and there are at least 3 earlier clear dates |
| `CLOUD_OBSCURED` | Clouds covered the field on every pass of the last 10 days; the patches of the last clear date are still shown, with that date |
| `PARTIAL` | Fewer than 3 earlier clear dates: there is no baseline yet, so nothing is called unusual |
| `NO_DATA` | No clear scene in 90 days |

"Nothing unusual" is only said with `GOOD`. A cloudy week is never "all fine".

## In the product

- The field card's **Something unusual** section: "Nothing unusual on 1 Oct (Sentinel-2)" in
  green, or in red "Less green in 12 ha, to the NE (1 Oct)", one line per patch; patches are drawn
  on the map while the card is open.
- A field split into lots shows its lots' patches, each with its lot ("Less green in 12 ha, to
  the N of Lote 3"), and is called fine only when every lot was seen on a recent clear date.
- A chip in the list when a field has a patch.
- The weekly and daily summaries list the patches.
- The worker checks every 6 hours for new scenes; each field is analyzed once per new scene.
  Each date's indices are cached per field (`data/cache/sentinel2/fields/`), so a new scene reads
  one date, not 90 days.
- It is an observation from orbit, not a diagnosis: the card says what changed and where, and that
  someone should look. Clouds the classification missed, a recent partial harvest or a sprayed
  strip can also show up.
