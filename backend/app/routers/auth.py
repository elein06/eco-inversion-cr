"""
Flujo crítico F1 — Registro e inicio de sesión.

POST /auth/registro  crea una cuenta con rol "usuario" (nunca admin).
POST /auth/login     devuelve un JWT; bloquea la cuenta tras N fallos seguidos.
GET  /auth/yo        datos de la sesión actual.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from psycopg2 import errors as pg_errors
from psycopg2.extensions import cursor as Cursor
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app import eventos
from app.auth import (
    UsuarioSesion,
    crear_token,
    hashear_password,
    necesita_rehash,
    usuario_actual,
    verificar_password,
)
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["autenticación"])

# Mismo mensaje para email inexistente y contraseña incorrecta: no revela
# qué cuentas existen.
MENSAJE_CREDENCIALES = "Email o contraseña incorrectos."
MENSAJE_BLOQUEO = "Demasiados intentos fallidos. Intente de nuevo más tarde."


class RegistroEntrada(BaseModel):
    # extra="forbid": un campo "rol" o "usuario_id" en el cuerpo es un 422,
    # no algo que se ignora en silencio (asignación masiva).
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    nombre: str | None = Field(default=None, max_length=100)


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (tipo de token, no un secreto)
    expira_en: int


@router.post("/registro", status_code=status.HTTP_201_CREATED, response_model=UsuarioSesion)
def registro(datos: RegistroEntrada, request: Request, cur: Cursor = Depends(get_db)):
    try:
        cur.execute(
            """
            INSERT INTO usuarios (email, nombre, password_hash, rol)
            VALUES (%s, %s, %s, 'usuario')
            RETURNING usuario_id, email, nombre, rol
            """,
            (datos.email.lower(), datos.nombre, hashear_password(datos.password)),
        )
    except pg_errors.UniqueViolation:
        cur.connection.rollback()
        eventos.registrar(
            "registro",
            "rechazado",
            request=request,
            motivo="email_duplicado",
            cuenta=eventos.huella(datos.email),
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese email."
        ) from None

    fila = cur.fetchone()
    cur.connection.commit()
    eventos.registrar("registro", "exito", request=request, usuario_id=fila["usuario_id"])
    return fila


@router.post("/login", response_model=TokenSalida)
def login(datos: LoginEntrada, request: Request, cur: Cursor = Depends(get_db)):
    cur.execute(
        """
        SELECT usuario_id, password_hash, activo, intentos_fallidos, bloqueado_hasta
        FROM usuarios WHERE lower(email) = lower(%s)
        FOR UPDATE
        """,
        (datos.email,),
    )
    fila = cur.fetchone()
    ahora = datetime.now(UTC)

    if fila is None:
        verificar_password(datos.password, None)  # iguala el tiempo de respuesta
        cur.connection.rollback()
        eventos.registrar(
            "login",
            "fallido",
            request=request,
            motivo="cuenta_inexistente",
            cuenta=eventos.huella(datos.email),
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAJE_CREDENCIALES)

    usuario_id = fila["usuario_id"]

    if fila["bloqueado_hasta"] is not None and fila["bloqueado_hasta"] > ahora:
        cur.connection.rollback()
        eventos.registrar("login", "bloqueado", request=request, usuario_id=usuario_id)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MENSAJE_BLOQUEO)

    if not verificar_password(datos.password, fila["password_hash"]) or not fila["activo"]:
        intentos = fila["intentos_fallidos"] + 1
        bloquear = intentos >= settings.login_max_intentos
        cur.execute(
            "UPDATE usuarios SET intentos_fallidos = %s, bloqueado_hasta = %s "
            "WHERE usuario_id = %s",
            (
                0 if bloquear else intentos,
                ahora + timedelta(minutes=settings.login_bloqueo_minutos) if bloquear else None,
                usuario_id,
            ),
        )
        cur.connection.commit()
        eventos.registrar(
            "login",
            "fallido",
            request=request,
            usuario_id=usuario_id,
            motivo="cuenta_inactiva" if not fila["activo"] else "password_incorrecta",
            intentos=intentos,
            cuenta_bloqueada=bloquear,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAJE_CREDENCIALES)

    nuevo_hash = (
        hashear_password(datos.password) if necesita_rehash(fila["password_hash"]) else None
    )
    cur.execute(
        """
        UPDATE usuarios
        SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = now(),
            password_hash = COALESCE(%s, password_hash)
        WHERE usuario_id = %s
        """,
        (nuevo_hash, usuario_id),
    )
    cur.connection.commit()

    token, expira_en = crear_token(usuario_id)
    eventos.registrar("login", "exito", request=request, usuario_id=usuario_id)
    return TokenSalida(access_token=token, expira_en=expira_en)


@router.get("/yo", response_model=UsuarioSesion)
def yo(usuario: UsuarioSesion = Depends(usuario_actual)):
    return usuario
