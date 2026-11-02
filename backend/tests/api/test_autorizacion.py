"""
Reglas de acceso por rol, propiedad del recurso y ausencia de sesión
(ítems 4.5 y 4.6). Cada rechazo comprueba además que los datos protegidos
no se expusieron ni cambiaron.
"""

import base64
import json

import pytest

from .conftest import PESOS


# ------------------------------------------------- F2: recalcular índice
def _fechas_indice(db):
    with db.cursor() as cur:
        cur.execute("SELECT canton_id, fecha_calculo FROM indice_viabilidad ORDER BY canton_id")
        return cur.fetchall()


def test_recalcular_sin_sesion_401_y_el_indice_no_cambia(client, db):
    antes = _fechas_indice(db)
    r = client.post("/indice-viabilidad/recalcular")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert _fechas_indice(db) == antes


def test_recalcular_como_usuario_403_y_el_indice_no_cambia(client, como, db):
    antes = _fechas_indice(db)
    r = client.post("/indice-viabilidad/recalcular", headers=como("ana"))
    assert r.status_code == 403
    assert _fechas_indice(db) == antes


def test_recalcular_como_admin_200(client, como, db):
    antes = _fechas_indice(db)
    r = client.post("/indice-viabilidad/recalcular", headers=como("admin"))
    assert r.status_code == 200
    assert r.json() == {"cantones_actualizados": 3}
    assert _fechas_indice(db) != antes


def test_rol_degradado_pierde_el_permiso_con_token_vigente(client, como, db, usuarios):
    cabeceras = como("admin")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET rol = 'usuario' WHERE usuario_id = %s", (usuarios["admin"],)
        )
    db.commit()
    assert client.post("/indice-viabilidad/recalcular", headers=cabeceras).status_code == 403


# --------------------------------------------- tokens manipulados o falsos
def _b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


@pytest.mark.parametrize(
    "cabecera",
    [
        "Bearer no-es-un-token",
        "Basic YWRtaW46YWRtaW4=",
        "Bearer "
        + _b64({"alg": "none"})
        + "."
        + _b64({"sub": "1", "exp": 9999999999, "iat": 1})
        + ".",
    ],
)
def test_token_invalido_401(client, cabecera):
    assert client.get("/escenarios", headers={"Authorization": cabecera}).status_code == 401
    r = client.post("/indice-viabilidad/recalcular", headers={"Authorization": cabecera})
    assert r.status_code == 401


def test_token_con_sub_cambiado_401(client, como, usuarios):
    token = como("beto")["Authorization"].split()[1]
    cab, _, firma = token.split(".")
    falso = f"{cab}.{_b64({'sub': str(usuarios['admin']), 'iat': 1, 'exp': 9999999999})}.{firma}"
    r = client.post("/indice-viabilidad/recalcular", headers={"Authorization": f"Bearer {falso}"})
    assert r.status_code == 401


# --------------------------------------- F3: escenarios (propiedad)
RUTAS_ESCENARIO = [
    ("GET", "/escenarios/{id}"),
    ("GET", "/escenarios/{id}/ranking"),
    ("GET", "/escenarios/{id}/export.csv"),  # ruta alternativa (4.6)
    ("DELETE", "/escenarios/{id}"),
]


@pytest.mark.parametrize("metodo,ruta", RUTAS_ESCENARIO)
def test_escenario_sin_sesion_401(client, escenario_de_ana, metodo, ruta):
    r = client.request(metodo, ruta.format(id=escenario_de_ana["escenario_id"]))
    assert r.status_code == 401
    assert "Ecoturismo" not in r.text


@pytest.mark.parametrize("quien", ["beto", "admin"])
@pytest.mark.parametrize("metodo,ruta", RUTAS_ESCENARIO)
def test_escenario_de_otro_404_sin_exponer_datos(
    client, como, escenario_de_ana, quien, metodo, ruta, db
):
    eid = escenario_de_ana["escenario_id"]
    r = client.request(metodo, ruta.format(id=eid), headers=como(quien))
    assert r.status_code == 404
    assert "Ecoturismo" not in r.text and "Cantón Alfa" not in r.text
    with db.cursor() as cur:  # sigue existiendo (el DELETE ajeno no borró nada)
        cur.execute("SELECT nombre FROM escenarios WHERE escenario_id = %s", (eid,))
        assert cur.fetchone()["nombre"] == "Ecoturismo norte"


@pytest.mark.parametrize("quien", ["beto", "admin"])
def test_modificar_escenario_de_otro_404_y_no_cambia(client, como, escenario_de_ana, db, quien):
    eid = escenario_de_ana["escenario_id"]
    r = client.put(
        f"/escenarios/{eid}",
        headers=como(quien),
        json={"nombre": "Hackeado", "pesos": PESOS, "cantones": []},
    )
    assert r.status_code == 404
    with db.cursor() as cur:
        cur.execute("SELECT nombre, cantones FROM escenarios WHERE escenario_id = %s", (eid,))
        fila = cur.fetchone()
    assert fila["nombre"] == "Ecoturismo norte"
    assert fila["cantones"] == [1, 2, 3]


def test_listado_solo_muestra_los_propios(client, como, escenario_de_ana):
    assert client.get("/escenarios", headers=como("beto")).json() == []
    propios = client.get("/escenarios", headers=como("ana")).json()
    assert [e["escenario_id"] for e in propios] == [escenario_de_ana["escenario_id"]]


def test_no_se_puede_crear_escenario_a_nombre_de_otro(client, como, usuarios):
    r = client.post(
        "/escenarios",
        headers=como("beto"),
        json={"nombre": "x", "pesos": PESOS, "usuario_id": usuarios["ana"]},
    )
    assert r.status_code == 422


def test_acceso_ajeno_queda_registrado(client, como, escenario_de_ana, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="eco.seguridad"):
        client.get(f"/escenarios/{escenario_de_ana['escenario_id']}", headers=como("beto"))
    eventos = [json.loads(r.message) for r in caplog.records if r.name == "eco.seguridad"]
    assert any(e["evento"] == "acceso_denegado" and e["motivo"] == "no_es_dueno" for e in eventos)


# ------------------------------------------------ rutas públicas siguen públicas
@pytest.mark.parametrize("ruta", ["/indice-viabilidad", "/zonas", "/health", "/health/listo"])
def test_rutas_publicas_sin_sesion(client, ruta):
    assert client.get(ruta).status_code == 200
