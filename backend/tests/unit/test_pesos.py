"""Reglas R1-R4 de app/pesos.py: casos válidos, errores y valores límite."""

import math

import pytest

from app.pesos import FactoresInvalidos, PesosInvalidos, combinar_factores, validar_pesos

IGUALES = {"ambiental": 0.25, "inversion": 0.25, "conectividad": 0.25, "seguridad": 0.25}
FACTORES = {"ambiental": 80, "inversion": 40, "conectividad": 60, "seguridad": 20}


# --------------------------------------------------------------- R1: claves
def test_pesos_validos_se_devuelven_como_float():
    assert validar_pesos({**IGUALES, "ambiental": 0.25}) == IGUALES


@pytest.mark.parametrize("clave", ["ambiental", "inversion", "conectividad", "seguridad"])
def test_falta_una_clave(clave):
    pesos = {k: v for k, v in IGUALES.items() if k != clave}
    with pytest.raises(PesosInvalidos, match="faltan"):
        validar_pesos(pesos)


def test_clave_extra_se_rechaza():
    with pytest.raises(PesosInvalidos, match="sobran"):
        validar_pesos({**IGUALES, "economia": 0.0})


# ----------------------------------------------------------- R2: rango/tipo
@pytest.mark.parametrize("valor", [-0.01, 1.01, math.nan, math.inf, "0.25", None, True])
def test_peso_fuera_de_rango_o_no_numerico(valor):
    pesos = {**IGUALES, "ambiental": valor}
    with pytest.raises(PesosInvalidos):
        validar_pesos(pesos)


def test_limites_0_y_1_son_validos():
    assert validar_pesos({"ambiental": 1, "inversion": 0, "conectividad": 0, "seguridad": 0})


# --------------------------------------------------------------- R3: suma
@pytest.mark.parametrize("delta", [0.001, -0.001, 0.0005])
def test_suma_dentro_de_la_tolerancia(delta):
    validar_pesos({**IGUALES, "ambiental": 0.25 + delta})


@pytest.mark.parametrize("delta", [0.0011, -0.0011, 0.25])
def test_suma_fuera_de_la_tolerancia(delta):
    with pytest.raises(PesosInvalidos, match="sumar 1"):
        validar_pesos({**IGUALES, "ambiental": 0.25 + delta})


def test_todos_en_cero_se_rechaza():
    with pytest.raises(PesosInvalidos, match="sumar 1"):
        validar_pesos(dict.fromkeys(IGUALES, 0))


# ------------------------------------------------------ R4: combinación
def test_combinacion_con_pesos_iguales_es_el_promedio():
    assert combinar_factores(FACTORES, IGUALES) == 50.0


def test_combinacion_con_pesos_distintos():
    pesos = {"ambiental": 0.4, "inversion": 0.1, "conectividad": 0.3, "seguridad": 0.2}
    # 80*0.4 + 40*0.1 + 60*0.3 + 20*0.2 = 32 + 4 + 18 + 4 = 58
    assert combinar_factores(FACTORES, pesos) == 58.0


def test_peso_unico_devuelve_ese_factor():
    pesos = {"ambiental": 0, "inversion": 0, "conectividad": 0, "seguridad": 1}
    assert combinar_factores(FACTORES, pesos) == 20.0


def test_extremos_0_y_100():
    assert combinar_factores(dict.fromkeys(FACTORES, 0), IGUALES) == 0.0
    assert combinar_factores(dict.fromkeys(FACTORES, 100), IGUALES) == 100.0


def test_tolerancia_no_saca_el_indice_de_0_100():
    pesos = {**IGUALES, "ambiental": 0.251}  # suma 1.001, dentro de tolerancia
    assert combinar_factores(dict.fromkeys(FACTORES, 100), pesos) == 100.0


def test_redondeo_a_dos_decimales():
    pesos = {"ambiental": 1 / 3, "inversion": 1 / 3, "conectividad": 1 / 3, "seguridad": 0}
    assert combinar_factores({**FACTORES, "conectividad": 61}, pesos) == 60.33


@pytest.mark.parametrize("valor", [-0.01, 100.01, math.nan, "50", None])
def test_factor_invalido(valor):
    with pytest.raises(FactoresInvalidos):
        combinar_factores({**FACTORES, "seguridad": valor}, IGUALES)


def test_factor_faltante():
    factores = {k: v for k, v in FACTORES.items() if k != "inversion"}
    with pytest.raises(FactoresInvalidos, match="inversion"):
        combinar_factores(factores, IGUALES)


def test_combinar_valida_los_pesos():
    with pytest.raises(PesosInvalidos):
        combinar_factores(FACTORES, {**IGUALES, "seguridad": 0.5})
