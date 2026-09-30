"use client";

import area from "@turf/area";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { TerraDraw, TerraDrawPolygonMode, ValidateNotSelfIntersecting } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

export type DrawnPolygon = { type: "Polygon"; coordinates: number[][][] };

export type FieldDrawing = {
  /** The closed polygon, once the user finishes drawing. */
  polygon: DrawnPolygon | null;
  /** Area in hectares of the shape being drawn, updated on every click. */
  hectares: number;
};

/** Polygon drawing on the map while `active` is true. Leaving draw mode discards the shape. */
export function useFieldDrawing(
  map: MapLibreMap | null,
  active: boolean,
  onClosed: () => void,
): FieldDrawing {
  const [drawing, setDrawing] = useState<FieldDrawing>({ polygon: null, hectares: 0 });
  const onClosedRef = useRef(onClosed);
  useEffect(() => {
    onClosedRef.current = onClosed;
  });

  useEffect(() => {
    if (!map || !active) return;
    const draw = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map }),
      modes: [
        new TerraDrawPolygonMode({
          validation: (feature) => ValidateNotSelfIntersecting(feature),
          styles: {
            fillColor: "#22d3ee",
            fillOpacity: 0.2,
            outlineColor: "#22d3ee",
            outlineWidth: 2,
            closingPointColor: "#ffffff",
            closingPointOutlineColor: "#22d3ee",
          },
        }),
      ],
    });
    draw.start();
    draw.setMode("polygon");

    const polygonOf = (id: string | number): DrawnPolygon | null => {
      const feature = draw.getSnapshotFeature(id);
      return feature?.geometry.type === "Polygon" ? (feature.geometry as DrawnPolygon) : null;
    };
    draw.on("change", (ids) => {
      const polygon = ids.map(polygonOf).find(Boolean);
      if (polygon) setDrawing((d) => ({ ...d, hectares: area(polygon) / 10_000 }));
    });
    draw.on("finish", (id) => {
      const polygon = polygonOf(id);
      if (!polygon) return;
      // One field per drawing: stop accepting clicks once the shape is closed.
      draw.setMode("static");
      setDrawing({ polygon, hectares: area(polygon) / 10_000 });
      onClosedRef.current();
    });
    return () => {
      draw.stop();
      setDrawing({ polygon: null, hectares: 0 });
    };
  }, [map, active]);

  return drawing;
}
