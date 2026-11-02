"""
Flujo crítico F3 — Escenarios privados de evaluación.

Un escenario guarda pesos propios para el índice y una lista corta de
cantones. Regla de acceso: SOLO el dueño puede ver, modificar, borrar,
calcular el ranking o exportar su escenario. Esto incluye a los admin: el
rol de admin sirve para operar el índice oficial, no para leer el trabajo
privado de otros usuarios.

Cuando alguien pide un escenario que no es suyo se responde 404 —igual que
si no existiera— para no revelar qué ids existen; el intento queda
registrado como evento "acceso_denegado".

La exportación CSV (ruta alternativa a los mismos datos, ítem 4.6) pasa por
la misma comprobación de propiedad que la vista normal.
"""

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from psycopg2.extensions import cursor as Cursor
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app import eventos
from app.auth import UsuarioSesion, usuario_actual
from app.database import get_db
from app.pesos import FACTORES, PesosInvalidos, combinar_factores, validar_pesos

router = APIRouter(prefix="/escenarios", tags=["escenarios (privados)"])

MAX_CANTONES = 84
COLUMNAS = "escenario_id, nombre, descripcion, pesos, cantones, creado_en, actualizado_en"


class Pesos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambiental: float
    inversion: float
    conectividad: float
    seguridad: float

    @model_validator(mode="after")
    def _reglas(self):
        try:
            validar_pesos(self.model_dump())
        except PesosInvalidos as exc:
            raise ValueError(str(exc)) from None
        return self


class EscenarioEntrada(BaseModel):
    # extra="forbid": no se puede colar usuario_id ni escenario_id en el cuerpo.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    pesos: Pesos
    cantones: list[int] = Field(default_factory=list, max_length=MAX_CANTONES)

    @field_validator("cantones")
    @classmethod
    def _cantones_validos(cls, valor: list[int]) -> list[int]:
        if any(c <= 0 for c in valor):
            raise ValueError("Los ids de cantón deben ser positivos.")
        if len(set(valor)) != len(valor):
            raise ValueError("La lista de cantones tiene repetidos.")
        return valor


# ------------------------------------------------------------------ helpers
def _a_salida(fila: dict) -> dict:
    pesos = fila["pesos"]
    return {**fila, "pesos": json.loads(pesos) if isinstance(pesos, str) else pesos}


def _exigir_cantones_existentes(cur: Cursor, cantones: list[int]) -> None:
    if not cantones:
        return
    cur.execute("SELECT canton_id FROM cantones WHERE canton_id = ANY(%s)", (cantones,))
    existentes = {f["canton_id"] for f in cur.fetchall()}
    faltan = sorted(set(cantones) - existentes)
    if faltan:
        raise HTTPException(422, f"Cantones inexistentes: {faltan}")


def _obtener_propio(
    cur: Cursor, escenario_id: int, usuario: UsuarioSesion, request: Request, accion: str
) -> dict:
    """Devuelve el escenario si es del usuario; si no, 404 + evento de seguridad."""
    cur.execute(
        f"SELECT usuario_id, {COLUMNAS} FROM escenarios WHERE escenario_id = %s", (escenario_id,)
    )
    fila = cur.fetchone()
    if fila is None or fila["usuario_id"] != usuario.usuario_id:
        if fila is not None:
            eventos.registrar(
                "acceso_denegado",
                "denegado",
                request=request,
                usuario_id=usuario.usuario_id,
                motivo="no_es_dueno",
                recurso="escenario",
                recurso_id=escenario_id,
                accion=accion,
            )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escenario no encontrado.")
    fila.pop("usuario_id")
    return fila


def _ranking(cur: Cursor, escenario: dict) -> list[dict]:
    pesos = escenario["pesos"]
    if isinstance(pesos, str):
        pesos = json.loads(pesos)
    cantones = escenario["cantones"]

    cur.execute(
        """
        SELECT iv.canton_id, c.nombre AS nombre_canton, c.provincia,
               iv.factor_ambiental, iv.factor_inversion,
               iv.factor_conectividad, iv.factor_seguridad,
               iv.indice_total AS indice_oficial
        FROM indice_viabilidad iv
        JOIN cantones c ON c.canton_id = iv.canton_id
        WHERE cardinality(%s::int[]) = 0 OR iv.canton_id = ANY(%s::int[])
        """,
        (cantones, cantones),
    )
    filas = []
    for f in cur.fetchall():
        factores = {k: float(f[f"factor_{k}"]) for k in FACTORES}
        filas.append(
            {
                "canton_id": f["canton_id"],
                "nombre_canton": f["nombre_canton"],
                "provincia": f["provincia"],
                **{f"factor_{k}": v for k, v in factores.items()},
                "indice_oficial": float(f["indice_oficial"]),
                "indice_escenario": combinar_factores(factores, pesos),
            }
        )
    filas.sort(key=lambda r: (-r["indice_escenario"], r["nombre_canton"]))
    return filas


def _celda_segura(valor: object) -> object:
    """Evita inyección de fórmulas al abrir el CSV en Excel/LibreOffice."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


# ------------------------------------------------------------------- rutas
@router.get("")
def listar(usuario: UsuarioSesion = Depends(usuario_actual), cur: Cursor = Depends(get_db)):
    """Escenarios del usuario en sesión (nunca los de otros)."""
    cur.execute(
        f"SELECT {COLUMNAS} FROM escenarios WHERE usuario_id = %s ORDER BY actualizado_en DESC",
        (usuario.usuario_id,),
    )
    return [_a_salida(f) for f in cur.fetchall()]


@router.post("", status_code=status.HTTP_201_CREATED)
def crear(
    datos: EscenarioEntrada,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    _exigir_cantones_existentes(cur, datos.cantones)
    cur.execute(
        f"""
        INSERT INTO escenarios (usuario_id, nombre, descripcion, pesos, cantones)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING {COLUMNAS}
        """,
        (
            usuario.usuario_id,
            datos.nombre,
            datos.descripcion,
            json.dumps(datos.pesos.model_dump()),
            datos.cantones,
        ),
    )
    fila = cur.fetchone()
    cur.connection.commit()
    return _a_salida(fila)


@router.get("/{escenario_id}")
def obtener(
    escenario_id: int,
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    return _a_salida(_obtener_propio(cur, escenario_id, usuario, request, "leer"))


@router.put("/{escenario_id}")
def actualizar(
    escenario_id: int,
    datos: EscenarioEntrada,
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    _obtener_propio(cur, escenario_id, usuario, request, "modificar")
    _exigir_cantones_existentes(cur, datos.cantones)
    # El WHERE repite usuario_id: aunque la comprobación de arriba fallara por
    # un error futuro, la base nunca actualizaría el escenario de otro.
    cur.execute(
        f"""
        UPDATE escenarios
        SET nombre = %s, descripcion = %s, pesos = %s, cantones = %s, actualizado_en = now()
        WHERE escenario_id = %s AND usuario_id = %s
        RETURNING {COLUMNAS}
        """,
        (
            datos.nombre,
            datos.descripcion,
            json.dumps(datos.pesos.model_dump()),
            datos.cantones,
            escenario_id,
            usuario.usuario_id,
        ),
    )
    fila = cur.fetchone()
    cur.connection.commit()
    return _a_salida(fila)


@router.delete("/{escenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(
    escenario_id: int,
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    _obtener_propio(cur, escenario_id, usuario, request, "borrar")
    cur.execute(
        "DELETE FROM escenarios WHERE escenario_id = %s AND usuario_id = %s",
        (escenario_id, usuario.usuario_id),
    )
    cur.connection.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{escenario_id}/ranking")
def ranking(
    escenario_id: int,
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    """Cantones del escenario ordenados por el índice calculado con SUS pesos."""
    escenario = _obtener_propio(cur, escenario_id, usuario, request, "ranking")
    return {"escenario": _a_salida(escenario), "ranking": _ranking(cur, escenario)}


@router.get("/{escenario_id}/export.csv")
def exportar_csv(
    escenario_id: int,
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    cur: Cursor = Depends(get_db),
):
    escenario = _obtener_propio(cur, escenario_id, usuario, request, "exportar")
    filas = _ranking(cur, escenario)

    columnas = [
        "canton_id",
        "nombre_canton",
        "provincia",
        *[f"factor_{k}" for k in FACTORES],
        "indice_oficial",
        "indice_escenario",
    ]
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=columnas)
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({k: _celda_segura(fila[k]) for k in columnas})

    eventos.registrar(
        "exportacion",
        "exito",
        request=request,
        usuario_id=usuario.usuario_id,
        recurso="escenario",
        recurso_id=escenario_id,
        filas=len(filas),
    )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="escenario-{escenario_id}.csv"',
            "Cache-Control": "no-store",
        },
    )
