"""Servidor local del sitio de LatentHealth.

Un solo proceso y un solo puerto: las rutas ``/api/...`` llaman a los modelos reales de
``src/latenthealth`` (que no se modifican) y el resto sirve el sitio compilado (``web/dist``).

Arranque (desde la raíz del repositorio)::

    powershell -ExecutionPolicy Bypass -File web\\start.ps1
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

WEB_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = WEB_DIR / "dist"

# En algunos Windows el registro asocia .js a text/plain y el navegador rechaza los módulos.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

app = FastAPI(
    title="LatentHealth · servidor local del sitio",
    description="Datos sintéticos. Prototipo de apoyo a la decisión, no diagnostica.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


class Health(BaseModel):
    status: str
    site_built: bool


@app.get("/api/health")
def health() -> Health:
    """Comprobación de vida: la web la usa para saber si el modelo está disponible."""
    return Health(status="ok", site_built=(DIST_DIR / "index.html").is_file())


class SPAStaticFiles(StaticFiles):
    """Archivos del sitio compilado; cualquier ruta que no sea un archivo devuelve index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            parts = path.replace("\\", "/").split("/")  # en Windows la ruta llega con "\"
            if exc.status_code == 404 and parts[0] != "api" and "." not in parts[-1]:
                return await super().get_response("index.html", scope)
            raise


def mount_site(application: FastAPI) -> None:
    """Monta el sitio compilado. Debe llamarse lo último, después de todas las rutas /api."""
    if DIST_DIR.is_dir():
        application.mount("/", SPAStaticFiles(directory=DIST_DIR, html=True), name="web")


mount_site(app)
