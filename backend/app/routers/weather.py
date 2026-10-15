import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.routers.dependencies import WeatherRootDep
from app.schemas import WeatherLayerOut
from app.services.weather_layer import STAMP, frame_path, layer_meta

router = APIRouter(tags=["weather"])


def _version(meta: dict) -> str:
    """Changes with the box or cell size, so a browser never shows a frame cached for another."""
    key = f"{meta['bbox']}{meta.get('cell')}".encode()
    return hashlib.sha1(key).hexdigest()[:6]


@router.get("/weather-layer", response_model=WeatherLayerOut)
def weather_layer(root: WeatherRootDep):
    """The clouds and rain loop: its frames, oldest first, and the box (docs/06-goes.md)."""
    meta = layer_meta(root)
    if meta is None or not meta["frames"]:
        raise HTTPException(404, "no clouds and rain frames yet")
    return {
        "bbox": meta["bbox"],
        "frames": [
            {"scanned_at": at, "id": f"{datetime.fromisoformat(at):{STAMP}}-{_version(meta)}"}
            for at in meta["frames"]
        ],
    }


@router.get("/weather-layer/{frame}.png", response_class=FileResponse)
def weather_frame(root: WeatherRootDep, frame: str):
    # "<scan>-<version>"; the version only tells caches apart.
    stamp, _, version = frame.partition("-")
    meta = layer_meta(root)
    if meta is None or version != _version(meta):
        raise HTTPException(404, "not a frame of the current layer")
    try:
        scanned_at = datetime.strptime(stamp, STAMP).replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(404, "not a frame") from exc
    path = frame_path(root, scanned_at)
    if not path.exists():
        raise HTTPException(404, "no frame of that scan")
    # A scan never changes once painted.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400, immutable"})
