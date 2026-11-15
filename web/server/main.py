"""Servidor local del sitio de LatentHealth.

Un solo proceso y un solo puerto: las rutas ``/api/...`` llaman a los modelos reales de
``src/latenthealth`` (que no se modifican) y el resto sirve el sitio (``web/site``).

Arranque (desde la raíz del repositorio)::

    powershell -ExecutionPolicy Bypass -File web\\start.ps1

La documentación interactiva de las rutas queda en ``/api/docs``.
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from .routes import chat, home, model

WEB_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = WEB_DIR / "site"  # el sitio: HTML, CSS y JavaScript sin paso de compilación
log = logging.getLogger("latenthealth.web")

# En algunos Windows el registro asocia .js a text/plain y el navegador rechaza los módulos.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")

_models_ready = threading.Event()


def _warm_up() -> None:
    """Carga los modelos en segundo plano para que la primera petición de la demo no espere."""
    for module in (home, model):
        try:
            module.warm_up()
        except Exception:  # la web debe arrancar aunque un modelo falle al precargarse
            log.exception("No se pudo precargar %s", module.__name__)
    _models_ready.set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_up, name="precarga-modelos", daemon=True).start()
    yield


app = FastAPI(
    title="LatentHealth · servidor local del sitio",
    description="Datos sintéticos. Prototipo de apoyo a la decisión, no diagnostica.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


class Health(BaseModel):
    status: str
    models_ready: bool
    site_built: bool


@app.get("/api/health", tags=["Estado"])
def health() -> Health:
    """Comprobación de vida: la web la usa para saber si el modelo está disponible."""
    return Health(
        status="ok",
        models_ready=_models_ready.is_set(),
        site_built=(DIST_DIR / "index.html").is_file(),
    )


app.include_router(home.router)
app.include_router(chat.router)
app.include_router(model.router)


class SPAStaticFiles(StaticFiles):
    """Archivos del sitio compilado; cualquier ruta que no sea un archivo devuelve index.html."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            parts = path.replace("\\", "/").split("/")  # en Windows la ruta llega con "\"
            if exc.status_code == 404 and parts[0] != "api" and "." not in parts[-1]:
                response = await super().get_response("index.html", scope)
            else:
                raise
        # El sitio cambia a menudo durante la demo: que el navegador pregunte siempre si hay versión nueva
        # (con ETag la respuesta es un 304 y no se vuelve a descargar).
        response.headers["Cache-Control"] = "no-cache"
        return response


# Siempre lo último: el sitio compilado ocupa todo lo que no sea /api.
if DIST_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=DIST_DIR, html=True), name="web")
