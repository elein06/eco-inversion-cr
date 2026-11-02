import logging
import re
import uuid
from contextlib import asynccontextmanager

import psycopg2
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg2.extensions import cursor as Cursor

from app import auth
from app.config import settings
from app.database import get_db
from app.routers import (
    ambiental,
    contratos,
    escenarios,
    indice,
    infraestructura,
    inversion,
    seguridad,
    zonas,
)
from app.routers import auth as auth_router

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("eco.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Sin JWT_SECRET válido la API no arranca: es preferible a arrancar con
    # sesiones firmadas con un secreto vacío o adivinable.
    auth.verificar_configuracion()
    yield


app = FastAPI(
    title="Eco-Inversión Costa Rica API",
    description=(
        "API propia que normaliza cuatro fuentes OSINT (SNIT, SICOP, OSM, OIJ) "
        "y calcula el Índice de Viabilidad por cantón. El frontend nunca habla "
        "directo con las fuentes originales."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

_REQUEST_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@app.middleware("http")
async def request_id(request: Request, call_next):
    """
    Identificador de correlación: se acepta el X-Request-ID entrante si tiene
    un formato seguro (para no inyectar basura en los logs) o se genera uno.
    Viaja en la respuesta y en cada evento de seguridad (app/eventos.py).
    """
    entrante = request.headers.get("X-Request-ID", "")
    request.state.request_id = entrante if _REQUEST_ID_VALIDO.match(entrante) else uuid.uuid4().hex
    respuesta = await call_next(request)
    respuesta.headers["X-Request-ID"] = request.state.request_id
    return respuesta


@app.exception_handler(psycopg2.OperationalError)
async def base_no_disponible(request: Request, exc: psycopg2.OperationalError):
    """Base caída, lenta o consulta cancelada por statement_timeout -> 503 limpio."""
    logger.warning(
        "base_no_disponible request_id=%s ruta=%s error=%s",
        getattr(request.state, "request_id", None),
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "La base de datos no está disponible. Intente de nuevo."},
        headers={"Retry-After": "5"},
    )


app.include_router(auth_router.router)
app.include_router(escenarios.router)
app.include_router(zonas.router)
app.include_router(contratos.router)
app.include_router(infraestructura.router)
app.include_router(seguridad.router)
app.include_router(indice.router)
app.include_router(ambiental.router)
app.include_router(inversion.router)


@app.get("/")
def raiz():
    return {
        "proyecto": "Eco-Inversión Costa Rica",
        "endpoints": [
            "/auth/registro",
            "/auth/login",
            "/auth/yo",
            "/escenarios",
            "/zonas",
            "/ambiental/capas",
            "/ambiental/capas/resumen",
            "/ambiental/factor",
            "/contratos-ambientales",
            "/inversion/factor",
            "/inversion/resumen",
            "/infraestructura",
            "/infraestructura/factor",
            "/infraestructura/resumen",
            "/seguridad",
            "/seguridad/factor",
            "/seguridad/resumen",
            "/indice-viabilidad",
            "/indice-viabilidad/recalcular",
            "/docs",
        ],
    }


@app.get("/health")
def health():
    """Vivo: el proceso responde. No toca la base."""
    return {"status": "ok"}


@app.get("/health/listo")
def health_listo(cur: Cursor = Depends(get_db)):
    """Listo: además la base responde. Si no, el handler de arriba da 503."""
    cur.execute("SELECT 1")
    return {"status": "ok", "base_de_datos": "ok"}
