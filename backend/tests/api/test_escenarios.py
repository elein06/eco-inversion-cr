"""F3 — Comportamiento de los escenarios para su dueño."""

import csv
import io

import pytest

from .conftest import PESOS


def test_crear_y_leer(client, como, escenario_de_ana):
    r = client.get(f"/escenarios/{escenario_de_ana['escenario_id']}", headers=como("ana"))
    assert r.status_code == 200
    assert r.json()["pesos"] == PESOS
    assert r.json()["cantones"] == [1, 2, 3]
    assert "usuario_id" not in r.json()


@pytest.mark.parametrize(
    "cambio,motivo",
    [
        ({"pesos": {**PESOS, "seguridad": 0.5}}, "sumar 1"),
        ({"pesos": {**PESOS, "ambiental": -0.1, "seguridad": 0.7}}, "entre 0 y 1"),
        ({"pesos": {k: v for k, v in PESOS.items() if k != "seguridad"}}, "seguridad"),
        ({"cantones": [1, 1]}, "repetidos"),
        ({"cantones": [0]}, "positivos"),
        ({"cantones": list(range(1, 86))}, "85"),
        ({"nombre": "   "}, "nombre"),
        ({"nombre": "x" * 101}, "nombre"),
    ],
)
def test_validaciones(client, como, cambio, motivo):
    cuerpo = {"nombre": "Prueba", "pesos": PESOS, "cantones": [], **cambio}
    r = client.post("/escenarios", headers=como("ana"), json=cuerpo)
    assert r.status_code == 422, r.text
    assert motivo in r.text


def test_canton_inexistente(client, como):
    r = client.post(
        "/escenarios",
        headers=como("ana"),
        json={"nombre": "x", "pesos": PESOS, "cantones": [1, 999]},
    )
    assert r.status_code == 422
    assert "999" in r.text


def test_ranking_usa_los_pesos_del_escenario(client, como, escenario_de_ana):
    r = client.get(f"/escenarios/{escenario_de_ana['escenario_id']}/ranking", headers=como("ana"))
    assert r.status_code == 200
    ranking = {f["canton_id"]: f for f in r.json()["ranking"]}
    # Alfa: 80*.4 + 40*.1 + 60*.3 + 20*.2 = 58 ; Beta: 8 + 9 + 9 + 14 = 40 ; tercero: 50
    assert ranking[1]["indice_escenario"] == 58.0
    assert ranking[2]["indice_escenario"] == 40.0
    assert ranking[3]["indice_escenario"] == 50.0
    assert [f["canton_id"] for f in r.json()["ranking"]] == [1, 3, 2]
    assert ranking[2]["indice_oficial"] == 52.5


def test_ranking_sin_cantones_usa_todos(client, como):
    r = client.post("/escenarios", headers=como("ana"), json={"nombre": "todos", "pesos": PESOS})
    rk = client.get(f"/escenarios/{r.json()['escenario_id']}/ranking", headers=como("ana"))
    assert len(rk.json()["ranking"]) == 3


def test_actualizar_y_borrar(client, como, escenario_de_ana):
    eid = escenario_de_ana["escenario_id"]
    nuevos = {"ambiental": 0, "inversion": 0, "conectividad": 0, "seguridad": 1}
    r = client.put(
        f"/escenarios/{eid}",
        headers=como("ana"),
        json={"nombre": "Solo seguridad", "pesos": nuevos, "cantones": [2]},
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Solo seguridad"
    rk = client.get(f"/escenarios/{eid}/ranking", headers=como("ana")).json()["ranking"]
    assert [(f["canton_id"], f["indice_escenario"]) for f in rk] == [(2, 70.0)]

    assert client.delete(f"/escenarios/{eid}", headers=como("ana")).status_code == 204
    assert client.get(f"/escenarios/{eid}", headers=como("ana")).status_code == 404


def test_exportar_csv(client, como, escenario_de_ana):
    r = client.get(
        f"/escenarios/{escenario_de_ana['escenario_id']}/export.csv", headers=como("ana")
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    filas = list(csv.DictReader(io.StringIO(r.text)))
    assert len(filas) == 3
    assert filas[0]["nombre_canton"] == "Cantón Alfa"


def test_csv_neutraliza_formulas(client, como, escenario_de_ana):
    r = client.get(
        f"/escenarios/{escenario_de_ana['escenario_id']}/export.csv", headers=como("ana")
    )
    nombres = [f["nombre_canton"] for f in csv.DictReader(io.StringIO(r.text))]
    malicioso = [n for n in nombres if "HYPERLINK" in n]
    assert malicioso and malicioso[0].startswith("'=")
