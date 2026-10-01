type Position = number[];

const EARTH_RADIUS_M = 6_371_008.8;

/** Local equirectangular projection to meters; accurate enough within one field. */
function toMeters([lon, lat]: Position, origin: Position): [number, number] {
  const rad = Math.PI / 180;
  return [
    (lon - origin[0]) * rad * EARTH_RADIUS_M * Math.cos(origin[1] * rad),
    (lat - origin[1]) * rad * EARTH_RADIUS_M,
  ];
}

function distanceToSegment(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): number {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
  const lengthSq = dx * dx + dy * dy;
  const t = lengthSq
    ? Math.max(
        0,
        Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq),
      )
    : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Douglas-Peucker on an open line: keeps the points that deviate more than `tolerance` meters. */
function simplifyLine(
  points: Position[],
  meters: [number, number][],
  tolerance: number,
): Position[] {
  if (points.length <= 2) return points;
  let worst = 0;
  let index = 0;
  for (let i = 1; i < points.length - 1; i++) {
    const d = distanceToSegment(
      meters[i],
      meters[0],
      meters[meters.length - 1],
    );
    if (d > worst) [worst, index] = [d, i];
  }
  if (worst <= tolerance) return [points[0], points[points.length - 1]];
  const left = simplifyLine(
    points.slice(0, index + 1),
    meters.slice(0, index + 1),
    tolerance,
  );
  const right = simplifyLine(
    points.slice(index),
    meters.slice(index),
    tolerance,
  );
  return [...left.slice(0, -1), ...right];
}

/**
 * Simplifies a closed ring (first point equals last). A traced outline has a point every few
 * pixels; after simplifying, the handles left are few enough to drag with a finger.
 */
export function simplifyRing(
  ring: Position[],
  toleranceMeters: number,
): Position[] {
  if (ring.length <= 5) return ring;
  const meters = ring.map((p) => toMeters(p, ring[0]));
  // Split at the point farthest from the start so both halves are open lines.
  let far = 1;
  for (let i = 1; i < ring.length - 1; i++) {
    if (Math.hypot(...meters[i]) > Math.hypot(...meters[far])) far = i;
  }
  const first = simplifyLine(
    ring.slice(0, far + 1),
    meters.slice(0, far + 1),
    toleranceMeters,
  );
  const second = simplifyLine(
    ring.slice(far),
    meters.slice(far),
    toleranceMeters,
  );
  const simplified = [...first.slice(0, -1), ...second];
  return simplified.length >= 4 ? simplified : ring;
}
