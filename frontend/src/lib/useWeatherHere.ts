"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useState } from "react";

import { pixelAt, type SkyHere, skyOf } from "./weatherHere";

// Frames already read, by address: the loop goes over the same few again and again.
const pixels = new Map<string, Promise<ImageData | null>>();

function readFrame(url: string): Promise<ImageData | null> {
  let read = pixels.get(url);
  if (!read) {
    read = new Promise((resolve) => {
      const image = new Image();
      image.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return resolve(null);
        context.drawImage(image, 0, 0);
        resolve(context.getImageData(0, 0, canvas.width, canvas.height));
      };
      image.onerror = () => resolve(null);
      image.src = url;
    });
    if (pixels.size > 40) pixels.clear();
    pixels.set(url, read);
  }
  return read;
}

/** The sky in the middle of the map on the newest frame, so the layer says what it shows even
 * zoomed in on one field, where a thin veil is hard to see (docs/06-goes.md#clouds-and-rain-on-the-map). */
export function useWeatherHere(
  map: MapLibreMap | null,
  frameUrl: string | null,
  bbox: [number, number, number, number] | null,
): SkyHere | null {
  const [center, setCenter] = useState<[number, number] | null>(null);
  const [sky, setSky] = useState<SkyHere | null>(null);

  useEffect(() => {
    if (!map) return;
    const update = () => {
      const { lng, lat } = map.getCenter();
      setCenter([lng, lat]);
    };
    update();
    map.on("moveend", update);
    return () => {
      map.off("moveend", update);
    };
  }, [map]);

  useEffect(() => {
    if (!frameUrl || !bbox || !center) return;
    let current = true;
    readFrame(frameUrl).then((data) => {
      if (!current) return;
      const spot = data && pixelAt(bbox, data.width, data.height, ...center);
      if (!data || !spot) return setSky(null);
      // A few cells around the middle: about 10 km across.
      const [x, y] = spot;
      const around: number[] = [];
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const px = Math.min(data.width - 1, Math.max(0, x + dx));
          const py = Math.min(data.height - 1, Math.max(0, y + dy));
          const i = (py * data.width + px) * 4;
          around.push(...data.data.slice(i, i + 4));
        }
      }
      setSky(skyOf(new Uint8ClampedArray(around)));
    });
    return () => {
      current = false;
    };
  }, [frameUrl, bbox, center]);

  return frameUrl && bbox ? sky : null;
}
