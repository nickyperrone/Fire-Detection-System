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
| `ABI-L2-ACHAF` | Cloud top height (m), about 10 km per pixel, full disk | 10 min | ~15 min | ~1.6 MB |
| `ABI-L2-RRQPEF` | Rainfall rate (mm/h), about 2 km per pixel, full disk | 10 min | ~10 min | ~1.6 MB |

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

## How recent the satellite look is

Polar satellites (VIIRS, MODIS through FIRMS) see small fires best but pass over Larroque a few
times a day, and FIRMS publishes each pass about 3 h later: their newest detection is often 6 to
12 hours old. GOES-19 looks at the whole region every 10 minutes. "When did a satellite last
look" is therefore GOES-19's newest scan read, from the file name of the last fire product
processed (`s{year}{day}{hour}{minute}`), not the newest detection: no detection means nothing
burned, not that nobody looked.

- `GET /health` returns `latest_scan` (GOES-19's newest fire scan) beside `latest_pass` (the
  newest polar pass with a detection).
- The status dock shows the newer of the two ("GOES-19 · 12 min ago"); its detail lists both,
  each with how often it looks.

## Clouds and rain on the map

"Nubes y lluvia" in the layers menu plays GOES-19's last two hours over Argentina, like a
weather radar loop, so the contractor sees where it is cloudy, where it rains and where it is
heading:

- **Clouds** from `ABI-L2-ACHAF` (cloud top height): a veil from 14 % to 40 % opaque, stronger
  the higher the tops, so a cloudy day does not turn the map gray. A high top alone is often a thin anvil
  of cirrus, not a storm, so height never paints a storm: rain does. Edges fade in, since the
  product's pixels are 10 km wide.
- **Rain** from `ABI-L2-RRQPEF` (rainfall rate), on top: light blue from 0.5 mm/h, blue from
  2.5 mm/h and violet from 10 mm/h. Less than 0.5 mm/h is not drawn.
- **Where.** All of Argentina, Islas Malvinas and the sea around them: the box
  `[-76, -56.5, -50, -20.5]` at 0.03° (about 3 km, finer than the cloud product), painted only
  over the country buffered by 1.4° (`coverage_buffer_degrees`) and fading out over a few cells,
  so there is no box edge and neighboring countries stay clear. Natural Earth draws the islands
  apart from the country; the layer adds them. Each frame is about 200 KB, the loop about 2.4 MB.
- **The loop.** The worker keeps one frame per scan for the last two hours (12 frames, one every
  10 minutes): on each run it paints every scan of that window it does not have yet and deletes
  older ones. Only the region's window of each file is read; it is reprojected to a grid even
  in longitude and in Web Mercator rows, so the map can stretch each image over the box.
- **On the map** every frame is an image layer over the box; playing fades from one to the next
  (about 0.6 s each, a short pause on the newest). The legend shows the scale, play and pause,
  and the time of the frame on screen ("hace 40 min" … "hace 10 min"). Paused, it shows the
  newest scan. People who ask their system for less motion get it paused. Zoomed in on a field,
  a 3 km cell covers the whole screen and a veil is hard to tell from the ground, so the legend
  also says in words what the newest frame shows around the middle of the map ("☁️ Nublado en
  esta zona", "🌧️ Llueve en esta zona", "☀️ Despejado en esta zona"). The browser reads it from
  the frame itself (`frontend/src/lib/weatherHere.ts`); the layer stays on wherever the map goes,
  a field page included, until it is turned off.
- `GET /weather-layer` lists the frames and the box; each frame's id is its scan time and a
  version of the box and cell size, and `GET /weather-layer/{id}.png` serves it, cached for a day.
  A change of box or cell size draws every frame again under new ids, so no browser shows a frame
  cached for the old box.
- It is GOES's estimate from space: rain rate comes from cloud temperatures, not from a rain gauge
  or a radar.

## Colors

One rule for the whole product: red when something is wrong (a fire near the field, spraying
not recommended or only with caution, lightning nearby), green when everything is fine, gray
when there is no data to say either. How serious it is goes in the text ("Inside", "Very close",
"Caution"), not in extra colors.

## Wind on the map

An animated layer of particles carried by the wind, switched on in the layers menu ("Viento", `wd=1`
in the link), readable at any zoom.

- **Data.** The worker (`wind` job, every hour) reads Open-Meteo's current 10 m wind on a grid over
  `[-76, -56.5, -50, -20.5]` every 1.5° (about 165 km; 450 points, 5 requests), turns
  speed and the direction it comes from into east and north components in km/h, and writes
  `data/weather/wind.json`. A point with no answer takes its neighbor's; with more than a quarter
  missing, or if Open-Meteo is down, the last grid stays. `GET /wind-layer` serves it.
- **Drawing.** The browser draws on a canvas over the map, not on the map's layers. Each time the
  map stops, it samples the grid (interpolated between the four nearest points) at a lattice of
  screen points every 18 px; 500 to 2,600 particles read that lattice and move
  0.05 px per frame per km/h, leaving a fading trail. Because the speed is in screen pixels, the
  flow looks the same at country zoom and over one field. Colors go from pale blue (calm) through
  green and yellow to orange (50 km/h and more).
- **While the map moves** the layer fades out and comes back when it stops, so it never lags behind
  the ground. People who ask their system for less motion get one still picture of the flow.
- It is off while drawing a field. Open-Meteo's free API is for non-commercial use only, as for the
  forecast.
