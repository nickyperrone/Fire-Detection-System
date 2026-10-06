# 12 — The field page and its satellite photos

A contractor watches many fields and, now and then, one closely: how the crop came up, where the
low corner flooded, whether the strip that was sprayed off is greening again. The field page is
that close look, and the place to manage a field.

## Navigation

- **Breadcrumbs** at the top of the panel are the way back, one step per level:
  `Mis campos › La Esperanza` above the title "Lote 3". The page's own name is the title, so it is
  not repeated in them, and "Mis campos" is always there, on a phone too.
- The open field and tab are in the link (`?f=12&tab=photos`), so the browser's back button, a
  reload and a shared link all land on the same page.
- **Escape** goes one step back up the breadcrumbs; with the photos full screen, it only closes
  them.
- The page's name, chips and tabs stay at the top while it scrolls; another tab starts at its top.

## Tabs

A segmented control under the field's name, with four tabs:

| Tab | What it holds |
|---|---|
| **Ahora** | A field's lots first, each with a dot that says whether it needs a look; then the answers for today: fire, spraying (with the 48 h timeline), weather, lightning, unusual patches and the fire forecast. |
| **Fotos** | The satellite photos of the field, one per clear pass, and how green it was over time. |
| **Historial** | Fires near the field in past years, by month. |
| **Ajustes** | Alerts, priority and visibility, tags, the lots of the field, editing the outline and deleting. |

Each lot opens its own page, from Ahora or Ajustes. A lot's page shows its field in the
breadcrumbs.

## The list

"Mis campos" is for watching many fields at once, so what needs a look comes first:

1. A fire near the field or one of its lots.
2. Lightning nearby.
3. Something unusual in it.
4. Not good to spray now.
5. Nothing to see.

A field ranks by its worst lot; fields marked high priority go first within a rank. A field with
nothing to report is one quiet line ("Todo en orden" and the weather) with a green dot; chips
appear only for what is wrong. Lots fold under their field ("15 lotes · 2 para mirar") and open as
thin rows. A lot is "para mirar" for what is its own: a fire, lightning or an unusual patch.
Spraying is not counted for lots: their weather is their field's, and the field already says it. The summary above the list counts fires, fields good to spray and fields with
something unusual.

## Satellite photos

Every Sentinel-2 pass over a field (every 2 to 5 days) that is clear enough over it is kept as a
photo. They are the same free Copernicus images the unusual-patches check already reads
([11-field-anomalies](11-field-anomalies.md)), so they cost no extra download for a field without
lots.

- **Which passes.** The last 180 days at first, then each new pass. A pass is kept when clouds and
  their shadows cover at most half of the field; the share of cloud is shown with the photo.
- **Two views of each pass.**
  - **Color real**: red, green and blue as the eye would see it. One fixed brightness for every
    date (reflectance × 3.2, then a light gamma), never stretched per photo, so a field that looks
    browner really is browner.
  - **Verdor**: NDVI painted from bare soil brown to dense green (-0.1 → 0.85), the same scale on
    every date. Clouds are gray.
- **The whole box around the field** is shown, with the field's outline drawn on top and its lots
  in thinner dashed lines. A lot's page shows its field's photos with that lot highlighted.
- **Greenness over time.** Below the photo, a line of the field's mean NDVI on each kept pass;
  tapping a point opens that photo. Sowing, growth and harvest read as the line rising and falling.
- **Compare.** A before/after slider over two dates: drag the divider to wipe from one to the
  other.
- **Full screen.** The photo opens large over the map, with the dates as a strip to scrub through
  and the arrow keys to step.

A photo is a record, not a diagnosis: a pass a few hours after rain, haze the cloud mask missed or a
low sun in winter change how it looks.

## How it is made

```
worker (every 6 h, images thread)
  for each field (not lots):
    field box, every pass of the lookback      -> data/cache/sentinel2/fields/   (shared with doc 11)
    skip passes already kept, or too cloudy over the field
    color real + verdor PNGs                   -> data/snapshots/{field}/{date}-{view}.png
    row: date, size, grid, cloud share, mean NDVI   -> field_snapshot
```

- Rasters stay out of Postgres: the table keeps the date, the image size, the grid (CRS and
  transform, to draw outlines on the image), the cloud share over the field and the mean NDVI.
- An edited outline changes the box: the old photos are dropped and the new box is read.
- `GET /territories/{id}/snapshots` lists the photos with each outline as an SVG path in image
  pixels; `GET /territories/{id}/snapshots/{date}/{view}.png` serves one, only to the field's
  owner.
- Thresholds are in `config/thresholds.yaml` (`snapshots`).
