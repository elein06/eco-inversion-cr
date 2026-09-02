from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class Zona(BaseModel):
    canton_id: int
    codigo_ine: str
    nombre: str
    provincia: str
    poblacion: int | None
    geom: dict[str, Any]  # GeoJSON


class ContratoAmbiental(BaseModel):
    contrato_id: int
    canton_id: int | None
    institucion: str
    municipalidad: str | None
    monto: float
    moneda: str
    fecha_contrato: date | None
    descripcion_objeto: str | None
    categoria_detectada: str
    fecha_consulta: datetime


class InfraestructuraOSM(BaseModel):
    poi_id: int
    canton_id: int | None
    categoria: str
    nombre: str | None
    geom: dict[str, Any]
    fecha_consulta: datetime
    valido_hasta: datetime


class EstadisticaSeguridad(BaseModel):
    estadistica_id: int
    canton_id: int
    tipo_delito: str
    cantidad: int
    anio: int
    fecha_consulta: datetime


class IndiceViabilidad(BaseModel):
    canton_id: int
    nombre_canton: str
    factor_ambiental: float
    factor_inversion: float
    factor_conectividad: float
    factor_seguridad: float
    indice_total: float
    pesos_usados: dict[str, float]
    fecha_calculo: datetime
    advertencia: str = (
        "El Factor de Seguridad usa estadísticas agregadas por cantón del OIJ. "
        "No implica nada sobre las personas residentes, y su relación con el "
        "índice de viabilidad es una correlación definida por el equipo, no "
        "una causalidad."
    )
