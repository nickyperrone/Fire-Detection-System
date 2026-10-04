# 10 — Field outlines by computer vision

Where there is no cadastre (Santa Fe, most provinces) or the parcel is not the field (one parcel
farmed as two lots, two parcels farmed as one), drawing by hand is the only way today. This adds a
fourth drawing tool, **Detect**: tap inside a field and its outline is found in satellite images.

## Idea

A field is the land farmed the same way. Over a year, every 10 m pixel of a field goes through the
same crop history (sown, green, ripe, harvested, fallow), and the field next door goes through a
different one, even when both look alike on a single date. So:

1. **Images.** The Sentinel-2 L2A scenes of the last 12 months over a 4 × 4 km window around the
   tap, at most one per month and under 10 % cloud (Earth Search STAC catalog, free Copernicus
   data on AWS). Only the window is read from each image (Cloud-Optimized GeoTIFF range requests):
   red, near infrared and the scene classification, about 200 kB per date.
2. **Crop history.** NDVI per date, with dates that have clouds or cloud shadow over more than 5 %
   of the window dropped (scene classification), smoothed with a small Gaussian. Each pixel
   becomes a curve of up to 12 values.
3. **Region growing.** The reference curve is the median of the 5 × 5 pixels around the tap. The
   field is the connected set of pixels, around the tap, whose curve is within a distance `τ`
   (root mean square difference of NDVI) of the reference, after a morphological opening that cuts
   one-pixel bridges, with holes (a tree, a puddle) filled.
4. **Outline.** A morphological closing fills the notches that weedy patches leave in the edge,
   holes are filled, and the region becomes one polygon without holes, simplified to 20 m. Most
   fields here are rectangles: when the shape fills at least 90 % of its minimum rotated
   rectangle, the rectangle is used (boundary regularization), which gives four clean corners to
   drag instead of a staircase of pixels. Coordinates are rounded to 7 decimals (about 1 cm).
   Then it goes through the same checks as any drawing.

A region that reaches the window's edge has no clear boundary (a big pasture, a lagoon, an urban
area): the answer is `no_field_found` and the user draws by hand. A field larger than the window
(over about 1,600 ha) is not found either; that is rare here.

This is classic computer vision (image segmentation by region growing on a multi-temporal stack),
with no model to train. A trained segmentation network is the next step if the benchmark shows the
need, measured with the same benchmark.

## Benchmark

The ground truth is the official cadastre (Entre Ríos, Buenos Aires, Córdoba): rural parcels of
20–400 ha, sampled at random. A parcel is not always a field, so the benchmark first keeps only the
parcels that are one field by the same evidence: at least 80 % of their pixels have a crop history
within `τ` of the parcel's median ("purity"). On those, the tap is the parcel's representative
point and the score is the IoU (intersection over union) between the outline found and the parcel.

`make field-detection-benchmark` downloads what it needs (cached in `data/cache/sentinel2/`), runs
the evaluation for each candidate `τ` and writes `docs/reports/field-detection.md`, committed with
each change to the method. The tool ships as an aid, not as truth: the card says the outline was
detected from images and asks to check it, and every point can still be dragged.

## In the map

- Draw mode has **Detect** next to Parcel, Trace and Corners. A tap shows "Detecting the field in
  satellite images…" (a few seconds: 12 dates are read in parallel), then the outline.
- The card says "Detected in Sentinel-2 images (12 dates, 12 Oct to 25 Sept). Check the
  outline." A detected outline is not fitted to property lines: it shows what the images say, and
  the Parcel tool is there for the cadastre's answer.
- `POST /fields/detect {lat, lon}` answers the polygon, the number of dates used and their range,
  or `no_field_found` / `no_images` (no clear dates in the last 12 months).
- Results are cached per tapped 100 m cell for a week: tapping the same field again is instant.
