"""
Autenticación y autorización.

- Contraseñas con argon2id (argon2-cffi). Nunca se guardan ni se registran.
- Sesión con JWT HS256 de corta duración, enviado como
  `Authorization: Bearer <token>`. El secreto viene de JWT_SECRET.
- El rol NO se toma del token: en cada solicitud se vuelve a leer el usuario
  de la base, así que desactivar una cuenta o quitarle el rol de admin tiene
  efecto inmediato aunque tenga un token vigente.

Dependencias para los routers:
    usuario_actual   -> 401 si no hay sesión válida
    requiere_admin   -> 401 sin sesión, 403 si no es admin
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg2.extensions import cursor as Cursor
from pydantic import BaseModel

from app import eventos
from app.config import settings
from app.database import get_db

ALGORITMO = "HS256"
LONGITUD_MINIMA_SECRETO = 32

_hasher = PasswordHasher()
# Hash de relleno: cuando el email no existe se verifica contra este, para
# que la respuesta tarde lo mismo y no revele qué cuentas existen.
_HASH_RELLENO = _hasher.hash("contraseña-de-relleno-que-nunca-coincide")

_bearer = HTTPBearer(auto_error=False)


class UsuarioSesion(BaseModel):
    usuario_id: int
    email: str
    nombre: str | None
    rol: str


# ---------------------------------------------------------------- contraseñas
def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _HASH_RELLENO, password)
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# --------------------------------------------------------------------- tokens
def _secreto() -> str:
    secreto = settings.jwt_secret
    if len(secreto) < LONGITUD_MINIMA_SECRETO:
        raise RuntimeError(
            f"JWT_SECRET no está configurado o tiene menos de {LONGITUD_MINIMA_SECRETO} "
            "caracteres. Generar uno con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return secreto


def verificar_configuracion() -> None:
    """Se llama al arrancar la API: sin secreto válido no se levanta."""
    _secreto()


def crear_token(usuario_id: int) -> tuple[str, int]:
    ahora = datetime.now(UTC)
    duracion = timedelta(minutes=settings.jwt_minutos)
    payload = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + duracion,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secreto(), algorithm=ALGORITMO), int(duracion.total_seconds())


def decodificar_token(token: str) -> int:
    """Devuelve el usuario_id o lanza jwt.InvalidTokenError."""
    payload = jwt.decode(
        token,
        _secreto(),
        algorithms=[ALGORITMO],  # lista cerrada: rechaza "none" y cambios de algoritmo
        options={"require": ["exp", "iat", "sub"]},
    )
    try:
        return int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise jwt.InvalidTokenError("sub inválido") from exc


# --------------------------------------------------------------- dependencias
def _no_autenticado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Se requiere iniciar sesión.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_actual(
    request: Request,
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    cur: Cursor = Depends(get_db),
) -> UsuarioSesion:
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        eventos.registrar("acceso_sin_sesion", "denegado", request=request)
        raise _no_autenticado()

    try:
        usuario_id = decodificar_token(credenciales.credentials)
    except jwt.InvalidTokenError as exc:
        eventos.registrar("token_invalido", "denegado", request=request, motivo=type(exc).__name__)
        raise _no_autenticado() from None

    cur.execute(
        "SELECT usuario_id, email, nombre, rol, activo FROM usuarios WHERE usuario_id = %s",
        (usuario_id,),
    )
    fila = cur.fetchone()
    if fila is None or not fila["activo"]:
        eventos.registrar(
            "token_usuario_inactivo", "denegado", request=request, usuario_id=usuario_id
        )
        raise _no_autenticado()

    request.state.usuario_id = fila["usuario_id"]
    return UsuarioSesion(
        usuario_id=fila["usuario_id"], email=fila["email"], nombre=fila["nombre"], rol=fila["rol"]
    )


def requiere_admin(
    request: Request, usuario: UsuarioSesion = Depends(usuario_actual)
) -> UsuarioSesion:
    if usuario.rol != "admin":
        eventos.registrar(
            "acceso_denegado",
            "denegado",
            request=request,
            usuario_id=usuario.usuario_id,
            motivo="requiere_admin",
            rol=usuario.rol,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación requiere rol de administrador.",
        )
    return usuario
