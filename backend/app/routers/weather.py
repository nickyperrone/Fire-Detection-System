from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.routers.dependencies import WeatherRootDep
from app.schemas import WeatherLayerOut
from app.services.weather_layer import IMAGE, layer_meta

router = APIRouter(tags=["weather"])


@router.get("/weather-layer", response_model=WeatherLayerOut)
def weather_layer(root: WeatherRootDep):
    """When the clouds and rain image was scanned and the box it covers (docs/06-goes.md)."""
    meta = layer_meta(root)
    if meta is None:
        raise HTTPException(404, "no clouds and rain image yet")
    return meta


@router.get("/weather-layer.png", response_class=FileResponse)
def weather_layer_image(root: WeatherRootDep):
    path = root / IMAGE
    if not path.exists():
        raise HTTPException(404, "no clouds and rain image yet")
    # The map asks with the scan time in the link, so a new scan is a new address.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=600"})
