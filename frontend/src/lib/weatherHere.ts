/** What the clouds and rain frame shows at one spot of the map (docs/06-goes.md#clouds-and-rain-on-the-map). */
export type SkyHere = "clear" | "clouds" | "light" | "moderate" | "heavy";

// The rain colors the worker paints (backend/app/vision/weather_layer.py), lightest first.
const RAIN: { name: SkyHere; rgb: [number, number, number] }[] = [
  { name: "light", rgb: [96, 165, 250] },
  { name: "moderate", rgb: [37, 99, 235] },
  { name: "heavy", rgb: [168, 85, 247] },
];
// Below this opacity the veil is the faded edge of a cloud: the sky there reads as clear.
const CLOUD_MIN_ALPHA = 12;

function mercatorY(lat: number): number {
  const rad = (lat * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + rad / 2));
}

/** The pixel of an image stretched over `bbox` that sits under a point: columns even in
 * longitude, rows even in Web Mercator, as the worker paints them. Null outside the image. */
export function pixelAt(
  bbox: [number, number, number, number],
  width: number,
  height: number,
  lon: number,
  lat: number,
): [number, number] | null {
  const [west, south, east, north] = bbox;
  if (lon < west || lon > east || lat < south || lat > north) return null;
  const x = ((lon - west) / (east - west)) * width;
  const top = mercatorY(north);
  const y = ((top - mercatorY(lat)) / (top - mercatorY(south))) * height;
  return [
    Math.min(width - 1, Math.floor(x)),
    Math.min(height - 1, Math.floor(y)),
  ];
}

/** The strongest weather among some RGBA pixels: rain over clouds over a clear sky. */
export function skyOf(pixels: Uint8ClampedArray): SkyHere {
  let best: SkyHere = "clear";
  const rank = (s: SkyHere) =>
    ["clear", "clouds", "light", "moderate", "heavy"].indexOf(s);
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b, a] = [
      pixels[i],
      pixels[i + 1],
      pixels[i + 2],
      pixels[i + 3],
    ];
    let sky: SkyHere = a >= CLOUD_MIN_ALPHA ? "clouds" : "clear";
    for (const band of RAIN) {
      const [br, bg, bb] = band.rgb;
      if (
        a > 0 &&
        Math.abs(r - br) + Math.abs(g - bg) + Math.abs(b - bb) < 30
      ) {
        sky = band.name;
      }
    }
    if (rank(sky) > rank(best)) best = sky;
  }
  return best;
}
