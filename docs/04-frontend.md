# 04 — Frontend

Phase 1. The user is in a truck or at the edge of a field, on a phone, often in the sun. The app
behaves like a navigation app: the map fills the screen, answers float above it, and nothing needs
more than two taps.

## Layout

```
┌──────────────────────────────┐
│ [ Search fields or places ] ⚙ │   floating search, rounded, over the map
│                              │
│        full-screen map       │
│   fields colored by status   │
│      fires as pulsing dots   │
│                              │
│                    [layers]  │   floating buttons, right edge
│                    [ ◎ me ]  │
│┌────────────────────────────┐│
││ ▔▔▔                        ││   bottom sheet, drag to expand
││ La Esperanza · 389 ha      ││
││ Fire   HIGH  3.7 km NE     ││
││ Spray  CAUTION  gusts 18   ││
││ Weird  no data yet         ││
│└────────────────────────────┘│
└──────────────────────────────┘
```

- **Map first.** No sidebar on mobile. On desktop the bottom sheet becomes a left panel of the same content.
- **Bottom sheet with three heights** (peek, half, full), as in Google Maps:
  - peek: the selected field and its three answers, or the portfolio summary ("2 fields need attention");
  - half: the portfolio list, worst first, with tag chips to filter;
  - full: field detail (fire history, 48 h spray timeline, sources and timestamps).
- **Status colors are the same everywhere** (map fill, chips, list): `CRITICAL`/`UNFAVORABLE` red,
  `VERY_HIGH`/`HIGH` orange, `WATCH`/`CAUTION` amber, `FAVORABLE` and no detections green,
  `NO_DATA`/`STALE` gray with a dashed outline. Color is never the only signal: every chip has text.
- **Spray timeline**: a horizontal strip of 48 hourly cells colored by status; tapping a cell shows
  the rule that failed. The next favorable window is labeled on the strip.
- **Drawing a field**: a floating "+" starts draw mode, tap corners, close the shape, hectares update
  live, then name and tags. A drawn field can be split into sections the same way.
- **Provenance in one tap**: every fire answer opens a card with sensors, confidence, "acquired 2 h ago ·
  received 5 min ago", and the processing version.
- **Visual style**: dark basemap by default (fires and colors read better, less glare), light basemap
  as an option, one accent color, large type for the three answers, system font stack. Smooth camera
  moves (`flyTo`) when selecting a field, like a navigation app.

## Progressive map loading

The map loads what is on screen, at the detail the zoom needs, like Google Maps.

- The backend serves **Mapbox Vector Tiles** straight from PostGIS: `GET /tiles/{layer}/{z}/{x}/{y}.pbf`
  built with `ST_AsMVTGeom` + `ST_AsMVT`. Layers: `territories`, `fire_events`, `observations`.
- MapLibre requests only the tiles in view, shows lower zoom tiles while higher ones arrive, and caches
  them. Panning and zooming never download the whole dataset.
- **Detail by zoom**: below zoom 9 fires are clustered (count + worst severity) and field outlines are
  simplified (`ST_SimplifyPreserveTopology` with a tolerance that depends on `z`); from zoom 12 individual
  observations and exact outlines appear.
- Tiles carry `Cache-Control` headers: short for fire layers (5 min), longer for territories, which
  are invalidated by a version parameter when a field changes.
- Portfolio and detail data (answers, timelines) come from the JSON API, not from tiles.

## Explore mode (no login)

- Anyone can open the map without an account and see fire events and observations for the covered
  regions, updated as the worker ingests them.
- Explore mode has no fields, no spray conditions and no notifications.
- Drawing a field, saving tags and receiving alerts require login (Phase 3). Email alerts are only
  sent to a verified address of a logged-in user with at least one field.

## Stack

Next.js (App Router), TypeScript, Tailwind, MapLibre GL JS, mapbox-gl-draw for drawing,
TanStack Query for API data. Filters, the selected field and the map view live in the URL, so every
view can be shared as a link.
