// MapLibre 6 starts its web worker from a separate ES module that the bundler does not emit,
// so the worker and the shared chunk it imports are served from public/ instead.
// Runs before dev and build so the files always match the installed maplibre-gl version.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "maplibre-gl", "dist");
const target = join(root, "public", "maplibre");

mkdirSync(target, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(source, file), join(target, file));
}
