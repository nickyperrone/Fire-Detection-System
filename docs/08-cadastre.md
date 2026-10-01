# 08 — Property lines (cadastre)

Fields follow property lines. Drawing them by eye over imagery is slow and inexact; the provinces
already publish the official parcels.

## Source

| Province | Publisher | Service | Layer | Terms |
|---|---|---|---|---|
| Entre Ríos | ATER, Dirección de Catastro | WFS `https://geoserver.ater.gob.ar/geoserver/sit_catastro/ows` | `sit_catastro:vwm_parcelario_base` | Capabilities declare no fees and no access constraints |

Each parcel has its outline (MultiPolygon), department, `partida` (tax account), `plano`
(survey plan) and a validation status ("Datos parcialmente validados"). The province's WMS paints
parcels with an opaque fill, which would hide the imagery, so the product reads the vector data and
draws its own thin lines.

Other provinces publish their own services (for example IDECOR in Córdoba, ARBA in Buenos Aires).
Each is one entry in `config/thresholds.yaml` (`cadastre.sources`); without one, the map has no
property lines there and fields are drawn by hand.

## Loading on demand

The region has about 556,000 parcels (15,800 around Larroque), most of them urban lots. Copying
them all would download hundreds of megabytes nobody looks at. Instead:

- Parcels are fetched per web-map tile at zoom 13 (about 5 × 5 km here) the first time that tile is
  needed, stored in `cadastral_parcel`, and the tile is recorded in `cadastral_tile`.
- After that the area is served from PostGIS as vector tiles (`/tiles/parcels/{z}/{x}/{y}.pbf`,
  zoom 13 and up) and does not depend on the province's server.
- A cached tile is refreshed after `cadastre.refresh_days` (90): parcels change slowly.
- Below zoom 13 there are no property lines: they would be a solid mesh.

## In the map

- "Property lines" in the layers menu, on by default, thin light lines that read over the dark,
  light and satellite basemaps.
- A shape drawn by hand (Trace or Corners) is fitted to the property lines when it closes,
  by the first rule that applies (`POST /cadastre/snap`):
  1. **Whole parcels.** Every parcel the drawing covers for at least half of its area is taken,
     and the field becomes the exact union of those parcels, as long as that union differs from
     the drawing by at most 35 % of the drawing's area. This is "I went roughly around these
     parcels".
  2. **Edges.** Otherwise, the drawing's points within 30 m of a property corner move into it,
     and those within 30 m of a property line move onto it; the rest stay where they were. This is "a lot inside a parcel that shares
     some of its edges".
  3. Neither: the drawing is kept as it is.
  The card says what happened ("Fitted to 3 parcels") and offers **Use my drawing**, which puts
  the original shape back; it can be fitted again. Thresholds are in `cadastre.snap`.
- Drawing a field has a third tool, **Parcel**: tap a parcel and its exact outline becomes the
  field, which can still be adjusted point by point. The parcel's department, `partida` and `plano`
  are kept in the field's attributes.
