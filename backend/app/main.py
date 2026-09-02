from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import contratos, indice, infraestructura, seguridad, zonas

app = FastAPI(
    title="Eco-Inversión Costa Rica API",
    description=(
        "API propia que normaliza cuatro fuentes OSINT (SNIT, SICOP, OSM, OIJ) "
        "y calcula el Índice de Viabilidad por cantón. El frontend nunca habla "
        "directo con las fuentes originales."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zonas.router)
app.include_router(contratos.router)
app.include_router(infraestructura.router)
app.include_router(seguridad.router)
app.include_router(indice.router)


@app.get("/")
def raiz():
    return {
        "proyecto": "Eco-Inversión Costa Rica",
        "endpoints": [
            "/zonas",
            "/contratos-ambientales",
            "/infraestructura",
            "/seguridad",
            "/indice-viabilidad",
            "/docs",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
