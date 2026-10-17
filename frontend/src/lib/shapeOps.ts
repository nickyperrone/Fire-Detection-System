import area from "@turf/area";
import difference from "@turf/difference";
import { featureCollection, polygon } from "@turf/helpers";
import intersect from "@turf/intersect";
import union from "@turf/union";

/** A field is one polygon, without holes (docs/04-frontend.md#drawing-a-field). */
export type Shape = { type: "Polygon"; coordinates: number[][][] };
type Area = GeoJSON.Polygon | GeoJSON.MultiPolygon;

/** Why an edit gave no new shape, or what it had to do to give one. */
export type EditNote =
  | "kept_largest" // the result had several pieces: the biggest stays
  | "piece_outside" // the piece does not touch the shape
  | "removed_all" // nothing would be left
  | "unusable" // the map's drawing layer would not take the result
  | "clipped" // a lot was cut to the edge of its field
  | "outside_parent"; // a lot has nothing inside its field

export type EditResult =
  { shape: Shape; note: EditNote | null } | { shape: null; note: EditNote };

// The drawing layer refuses coordinates with more than 9 decimals; boolean operations make them.
const DECIMALS = 8;
const rounded = (n: number) => Number(n.toFixed(DECIMALS));

/** The biggest piece of an area, without holes, with coordinates the drawing layer accepts. */
export function largest(geometry: Area): Shape {
  const parts =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const best = parts.reduce((a, b) =>
    area({ type: "Polygon", coordinates: b }) >
    area({ type: "Polygon", coordinates: a })
      ? b
      : a,
  );
  return {
    type: "Polygon",
    coordinates: [best[0].map(([x, y]) => [rounded(x), rounded(y)])],
  };
}

function finish(
  result: Area | null,
): { shape: Shape; note: EditNote | null } | null {
  if (!result) return null;
  const many = result.type === "MultiPolygon" && result.coordinates.length > 1;
  return { shape: largest(result), note: many ? "kept_largest" : null };
}

/** The shape with another zone joined to it. */
export function addPiece(base: Shape, piece: Shape): EditResult {
  const joined = union(
    featureCollection([polygon(base.coordinates), polygon(piece.coordinates)]),
  );
  return (
    finish(joined?.geometry ?? null) ?? { shape: null, note: "piece_outside" }
  );
}

/** The shape with a zone taken out of it. */
export function removePiece(base: Shape, piece: Shape): EditResult {
  const rest = difference(
    featureCollection([polygon(base.coordinates), polygon(piece.coordinates)]),
  );
  if (!rest) return { shape: null, note: "removed_all" };
  const untouched =
    area(rest) >= area({ type: "Feature", properties: {}, geometry: base }) - 1;
  if (untouched) return { shape: null, note: "piece_outside" };
  return finish(rest.geometry) as EditResult;
}

/** A shape cut to the edge of its parent, as a lot must be. */
export function clipTo(shape: Shape, parent: Area): EditResult {
  const parentFeature: GeoJSON.Feature<Area> = {
    type: "Feature",
    properties: {},
    geometry: parent,
  };
  const inside = intersect(
    featureCollection([polygon(shape.coordinates), parentFeature as never]),
  );
  if (!inside) return { shape: null, note: "outside_parent" };
  const clipped = finish(inside.geometry)!;
  const shrank =
    area(inside) <
    area({ type: "Feature", properties: {}, geometry: shape }) - 1;
  return { shape: clipped.shape, note: shrank ? "clipped" : clipped.note };
}
