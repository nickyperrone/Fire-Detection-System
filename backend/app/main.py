from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routers import (
    auth,
    cadastre,
    fields,
    fires,
    health,
    places,
    portfolio,
    tags,
    territories,
    tiles,
    weather,
)
from app.services.territories import TerritoryError

app = FastAPI(
    title="Field Watch API",
    description="Fire, spraying conditions and field anomalies per field and section.",
    version="0.1.0",
)
app.include_router(portfolio.router)
app.include_router(territories.router)
app.include_router(fires.router)
app.include_router(health.router)
app.include_router(tiles.router)
app.include_router(cadastre.router)
app.include_router(tags.router)
app.include_router(auth.router)
app.include_router(fields.router)
app.include_router(weather.router)
app.include_router(places.router)


@app.exception_handler(TerritoryError)
def territory_error_handler(request: Request, exc: TerritoryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc), "code": exc.code})
