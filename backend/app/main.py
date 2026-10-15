from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
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

# The interactive API docs are for development; in production the API is the app's, not public.
_development = not get_settings().app_url.startswith("https://")
app = FastAPI(
    title="Field Watch API",
    description="Fire, spraying conditions and field anomalies per field and section.",
    version="0.1.0",
    docs_url="/docs" if _development else None,
    redoc_url="/redoc" if _development else None,
    openapi_url="/openapi.json" if _development else None,
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


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """A page of another site cannot change anything here, nor sign someone in to its own account
    (docs/09-accounts-and-alerts.md#signing-in-a-link-by-email). Browsers send Origin on these
    requests; other clients, without one, still need the session cookie."""
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin is not None:
        app_url = urlparse(get_settings().app_url)
        if origin != f"{app_url.scheme}://{app_url.netloc}":
            return JSONResponse(
                status_code=403, content={"detail": "cross-site request", "code": "origin"}
            )
    response = await call_next(request)
    # The API's own pages (the sign-in confirmation) get the web's protections too.
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    return response


@app.exception_handler(TerritoryError)
def territory_error_handler(request: Request, exc: TerritoryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc), "code": exc.code})
