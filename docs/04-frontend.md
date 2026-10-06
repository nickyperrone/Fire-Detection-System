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
- **Two status colors, the same everywhere** (map fill, chips, list, timeline): red when something
  is wrong (any fire severity, `UNFAVORABLE` and `CAUTION` spraying, lightning nearby), green when
  all is fine, gray with a dashed outline for `NO_DATA`/`STALE`. How serious it is goes in the text
  ("Very close", "Caution"), never in extra colors.
- **Spray timeline**: a horizontal strip of 48 hourly cells colored by status; tapping a cell shows
  the rule that failed. The next favorable window is labeled on the strip.
- **Search** finds the user's fields, lots and tags first, then places in Argentina: addresses,
  streets, towns and areas ("Ruta 14 km 120", "Larroque", "Gualeguaychú"). Places come from
  OpenStreetMap through Photon (komoot), which is made for search as you type; the API proxies
  it (`GET /places?q=`, from 3 letters, results kept in memory for an hour) so the browser never
  calls it directly and repeated searches cost nothing. Picking a place frames its area, or flies
  to a street or address close enough to draw a field there.
- **Drawing a field**: a floating "+" starts draw mode, tap corners, close the shape, hectares update
  live, then name and tags. A drawn field can be split into sections the same way.
- **Corners never trap the user**: while placing corners a drag still moves the map (a tap places
  a corner, a drag pans), the card counts the corners and offers **Undo corner** (also Cmd or
  Ctrl+Z) and **Close field** from three corners on, besides tapping the first corner again.
- **Editing a field's outline**: the field card has **Edit outline**, which opens draw mode with two
  pencils, **Add** and **Remove**. With either one the user draws a piece with the usual tools
  (Parcel, Trace, Corners; a hand-drawn piece is fitted to the property lines too) and the card
  shows the area the field will have ("+12 ha · 401 ha"). Saving joins the piece to the field or
  cuts it out (`PATCH /territories/{id}/outline`); the same request with `preview: true` answers
  without saving, so the card shows the result and any problem before the user saves. The server
  checks the result as it checks a new field, and also:
  - removing must leave something, and the piece must overlap the field (`nothing_left`,
    `no_overlap`); adding a piece already inside it changes nothing (`no_change`);
  - a lot must stay inside its field, and a field must keep its lots inside it (`cuts_lots`).
  Hectares are recomputed and the field's fire risk is assessed again at once: a fire that is no
  longer near the field leaves its list. Spray and forecast answers follow on their next hourly run.
- **Provenance in one tap**: every fire answer opens a card with sensors, confidence, "acquired 2 h ago ·
  received 5 min ago", and the processing version.
- **Visual style**: dark basemap by default (fires and colors read better, less glare), with light and
  satellite basemaps in the layers button; satellite is what a contractor uses to recognize a field.
  One accent color, large type for the three answers, system font stack. Smooth camera moves
  (`flyTo`) when selecting a field, like a navigation app.
- **Fields stand out on every basemap**: a dark edge under each outline keeps red, green and tag
  colors readable over crops of any color on the satellite photo; outlines and labels grow with
  zoom; the selected field or lot glows white, and an open lot's dashed edge turns solid and as
  thick as a field's, so it stands out from the lots around it.
- **Motion is short and subtle**: the selected field's glow fades in after the camera arrives,
  content rises in when the sheet changes, list rows appear in a quick cascade, and buttons give a
  small press. Fires breathe like a live location dot. Everything holds still for people who set
  their system to reduce motion.
- **A status dock floats at the bottom**: one small glass bar, centered over the map, that answers
  "am I signed in and is the data fresh" at a glance. From left to right:
  - **Satellite data**: a dot (green when fresh, gray when `STALE`, `NO_DATA` or the API is
    unreachable) and how long ago a satellite last looked at the region ("12 min ago"), which is
    GOES-19's newest scan almost always ([06-goes](06-goes.md#how-recent-the-satellite-look-is)).
    Tapping it opens the detail: GOES-19's scan (every 10 minutes), the newest polar pass with a
    detection ("VIIRS NOAA-21 · 9 h ago", a few passes a day, published about 3 h later) and when
    we last checked.
  - **Portfolio**, signed in: how many fields and hectares are monitored ("3 fields · 412 ha").
  - **Language**: ES or EN; tapping switches. Spanish by default for Argentine browsers, the choice
    is kept in the browser. The API returns codes and numbers, never sentences, so every text the
    user reads is translated in the frontend.
  - **Account**: "Sign in" while signed out; signed in, the account's initial with a green dot,
    which opens the address, the summary frequency and sign out.

  The glass follows Apple's Liquid Glass: the map shows through blurred and more saturated, a light
  rim catches the top edge, and panels open upwards out of the bar. People who ask their system for
  less transparency get a solid bar. On a phone the dock sits just above the sheet and slides away
  while the sheet is open higher, so it never covers a field's answers; on a computer it is
  centered over the map, beside the panel.

## Opening and scope

- First visit (no camera in the link): the map shows Argentina for a moment and then flies to the
  fields around Larroque (about 3 s). A shared link opens straight at its own position.
- The map is not limited: it can be panned and zoomed over the whole world.
- Draw mode adds a gray layer over everything outside Argentina; drawing there is refused by the
  API (`outside_country`) with a translated message.
- The boundary comes from `GET /boundary` (Natural Earth, simplified to about 1 km for drawing).

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
- Portfolio and detail data (answers, timelines) come from the JSON API, not from tiles. Field tiles
  only carry `id`, `name` and `kind`; the map colors each field with MapLibre feature state set from
  the portfolio, so a status change does not invalidate any tile.

## Explore mode (no login)

- Anyone can open the map without an account and see fire events and observations for the covered
  regions, updated as the worker ingests them.
- Explore mode has no fields, no spray conditions and no notifications.
- Drawing a field, saving tags and receiving alerts require signing in with a link by email
  ([09-accounts-and-alerts](09-accounts-and-alerts.md)). Signed out, the bottom sheet invites to
  sign in where the field list would be, and "+" opens the sign-in card.

## Stack

| Piece | Choice | Why |
|---|---|---|
| App | Next.js (App Router), TypeScript strict, Tailwind | |
| Map | MapLibre GL JS | Open source, vector tiles, feature state |
| Drawing | Terra Draw with its MapLibre adapter | Supports MapLibre directly; mapbox-gl-draw needs patches for it |
| Area while drawing | `@turf/area` | Live hectares; the backend value is the one saved |
| Basemaps | CARTO Dark Matter and Positron (vector), Esri World Imagery (satellite raster) | Free with attribution, no API key |
| API data | TanStack Query | Caching and background refetch of the portfolio |
| API types | `openapi-typescript` from the FastAPI OpenAPI document (`make codegen`) | Types never drift from the backend; CI fails if they do |

- Components never call `fetch`; data access goes through the hooks in `src/api/queries.ts`.
- Filters, the selected field and the map view live in the URL, so every view can be shared as a link.
- In development, Next.js proxies `/api/*` to the FastAPI server, so there is no CORS setup.
