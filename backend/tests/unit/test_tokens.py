"""Tokens JWT y contraseñas (app/auth.py), sin base de datos."""

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app import auth
from app.config import settings


def test_token_ida_y_vuelta():
    token, expira = auth.crear_token(42)
    assert auth.decodificar_token(token) == 42
    assert expira == settings.jwt_minutos * 60


def test_token_expirado_se_rechaza():
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "iat": ahora - timedelta(hours=2), "exp": ahora - timedelta(hours=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        auth.decodificar_token(token)


def test_token_firmado_con_otro_secreto():
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "iat": ahora, "exp": ahora + timedelta(minutes=5)},
        "otro-secreto-" + "y" * 40,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        auth.decodificar_token(token)


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def test_token_alg_none_se_rechaza():
    ahora = int(datetime.now(UTC).timestamp())
    cabecera = _b64({"alg": "none", "typ": "JWT"})
    cuerpo = _b64({"sub": "1", "iat": ahora, "exp": ahora + 300})
    token = f"{cabecera}.{cuerpo}."
    with pytest.raises(jwt.InvalidTokenError):
        auth.decodificar_token(token)


def test_payload_modificado_invalida_la_firma():
    token, _ = auth.crear_token(1)
    cabecera, _, firma = token.split(".")
    ahora = int(datetime.now(UTC).timestamp())
    falso = f"{cabecera}.{_b64({'sub': '2', 'iat': ahora, 'exp': ahora + 300})}.{firma}"
    with pytest.raises(jwt.InvalidSignatureError):
        auth.decodificar_token(falso)


def test_token_sin_sub_se_rechaza():
    ahora = datetime.now(UTC)
    token = jwt.encode(
        {"iat": ahora, "exp": ahora + timedelta(minutes=5)}, settings.jwt_secret, algorithm="HS256"
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        auth.decodificar_token(token)


def test_secreto_corto_impide_arrancar(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "corto")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth.verificar_configuracion()


def test_password_hash_y_verificacion():
    h = auth.hashear_password("una-contraseña-larga")
    assert h.startswith("$argon2id$")
    assert "una-contraseña-larga" not in h
    assert auth.verificar_password("una-contraseña-larga", h)
    assert not auth.verificar_password("otra-contraseña", h)


def test_verificar_contra_hash_inexistente_o_corrupto():
    assert not auth.verificar_password("cualquiera", None)
    assert not auth.verificar_password("cualquiera", "no-es-un-hash")
