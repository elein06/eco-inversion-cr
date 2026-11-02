"""F1 — Registro e inicio de sesión."""

import json
import logging

from .conftest import PASSWORD


def test_registro_crea_usuario_normal(client):
    r = client.post(
        "/auth/registro", json={"email": "Nueva@Prueba.cr", "password": "una-clave-bien-larga"}
    )
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["rol"] == "usuario"
    assert cuerpo["email"] == "nueva@prueba.cr"
    assert "password" not in json.dumps(cuerpo)


def test_registro_no_permite_elegir_rol_admin(client, db):
    r = client.post(
        "/auth/registro",
        json={"email": "colado@prueba.cr", "password": "una-clave-bien-larga", "rol": "admin"},
    )
    assert r.status_code == 422
    with db.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM usuarios WHERE email = 'colado@prueba.cr'")
        assert cur.fetchone()["n"] == 0


def test_registro_email_duplicado_sin_distinguir_mayusculas(client):
    r = client.post(
        "/auth/registro", json={"email": "ANA@prueba.cr", "password": "una-clave-bien-larga"}
    )
    assert r.status_code == 409


def test_registro_password_corta(client):
    r = client.post("/auth/registro", json={"email": "x@prueba.cr", "password": "corta"})
    assert r.status_code == 422


def test_login_exitoso_y_yo(client):
    r = client.post("/auth/login", json={"email": "ana@prueba.cr", "password": PASSWORD})
    assert r.status_code == 200
    token = r.json()["access_token"]
    yo = client.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert yo.status_code == 200
    assert yo.json()["email"] == "ana@prueba.cr"


def test_mismo_error_para_password_incorrecta_y_cuenta_inexistente(client):
    a = client.post("/auth/login", json={"email": "ana@prueba.cr", "password": "incorrecta"})
    b = client.post("/auth/login", json={"email": "nadie@prueba.cr", "password": "incorrecta"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_bloqueo_tras_intentos_fallidos(client):
    for _ in range(5):
        r = client.post("/auth/login", json={"email": "beto@prueba.cr", "password": "mala"})
        assert r.status_code == 401
    # Bloqueada: ni con la contraseña correcta entra.
    r = client.post("/auth/login", json={"email": "beto@prueba.cr", "password": PASSWORD})
    assert r.status_code == 429


def test_cuenta_desactivada_no_puede_usar_su_token(client, como, db, usuarios):
    cabeceras = como("ana")
    with db.cursor() as cur:
        cur.execute("UPDATE usuarios SET activo = FALSE WHERE usuario_id = %s", (usuarios["ana"],))
    db.commit()
    assert client.get("/auth/yo", headers=cabeceras).status_code == 401


def test_login_fallido_queda_registrado_sin_la_password(client, caplog):
    with caplog.at_level(logging.INFO, logger="eco.seguridad"):
        client.post(
            "/auth/login",
            json={"email": "ana@prueba.cr", "password": "clave-secreta-que-no-debe-salir"},
        )
    eventos = [json.loads(r.message) for r in caplog.records if r.name == "eco.seguridad"]
    fallidos = [e for e in eventos if e["evento"] == "login" and e["resultado"] == "fallido"]
    assert fallidos, eventos
    assert fallidos[-1]["usuario_id"] is not None
    assert fallidos[-1]["request_id"]
    assert "clave-secreta-que-no-debe-salir" not in caplog.text
    assert "ana@prueba.cr" not in caplog.text
