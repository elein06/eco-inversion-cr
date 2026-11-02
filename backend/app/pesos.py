"""
Reglas de negocio del Índice de Viabilidad: validación de pesos y
combinación de factores.

Funciones puras (sin base de datos) para poder probarlas en aislamiento
(tests/unit/test_pesos.py). Las usan tanto el cálculo oficial
(app/indice.py, con los pesos de config.py) como los escenarios privados de
cada usuario (app/routers/escenarios.py, con sus propios pesos).

Reglas:
  R1. Hay exactamente cuatro pesos: ambiental, inversion, conectividad, seguridad.
  R2. Cada peso es un número finito entre 0 y 1, ambos incluidos.
  R3. Los cuatro suman 1, con una tolerancia de ±0.001 (redondeo de la UI).
  R4. Cada factor está entre 0 y 100; el índice resultante también, con dos
      decimales.
"""

import math
from collections.abc import Mapping

FACTORES: tuple[str, ...] = ("ambiental", "inversion", "conectividad", "seguridad")
TOLERANCIA_SUMA = 0.001
# Margen para el error de punto flotante: 0.25+0.25+0.25+0.249 da
# 0.9990000000000001, que debe aceptarse como "exactamente 0.001 de diferencia".
_EPSILON = 1e-9


class PesosInvalidos(ValueError):
    """Los pesos no cumplen R1-R3."""


class FactoresInvalidos(ValueError):
    """Los factores no cumplen R4."""


def _es_numero(valor: object) -> bool:
    # bool es subclase de int en Python: True no debe pasar como peso 1.
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def validar_pesos(pesos: Mapping[str, object]) -> dict[str, float]:
    """Devuelve los pesos como dict[str, float] o lanza PesosInvalidos."""
    if not isinstance(pesos, Mapping):
        raise PesosInvalidos("Los pesos deben ser un objeto con cuatro claves.")

    claves = set(pesos)
    faltan = set(FACTORES) - claves
    sobran = claves - set(FACTORES)
    if faltan or sobran:
        partes = []
        if faltan:
            partes.append(f"faltan {sorted(faltan)}")
        if sobran:
            partes.append(f"sobran {sorted(sobran)}")
        raise PesosInvalidos("Claves de pesos inválidas: " + "; ".join(partes) + ".")

    resultado: dict[str, float] = {}
    for clave in FACTORES:
        valor = pesos[clave]
        if not _es_numero(valor) or not math.isfinite(valor):
            raise PesosInvalidos(f"El peso '{clave}' debe ser un número finito.")
        if not 0 <= valor <= 1:
            raise PesosInvalidos(f"El peso '{clave}' debe estar entre 0 y 1.")
        resultado[clave] = float(valor)

    suma = sum(resultado.values())
    if abs(suma - 1) > TOLERANCIA_SUMA + _EPSILON:
        raise PesosInvalidos(f"Los pesos deben sumar 1 (suman {suma:.4f}).")

    return resultado


def combinar_factores(factores: Mapping[str, object], pesos: Mapping[str, object]) -> float:
    """Suma ponderada de los cuatro factores (0-100), redondeada a 2 decimales."""
    pesos_validos = validar_pesos(pesos)

    total = 0.0
    for clave in FACTORES:
        if clave not in factores:
            raise FactoresInvalidos(f"Falta el factor '{clave}'.")
        valor = factores[clave]
        if not _es_numero(valor) or not math.isfinite(valor):
            raise FactoresInvalidos(f"El factor '{clave}' debe ser un número finito.")
        if not 0 <= valor <= 100:
            raise FactoresInvalidos(f"El factor '{clave}' debe estar entre 0 y 100.")
        total += float(valor) * pesos_validos[clave]

    # La tolerancia de R3 puede empujar el total unas centésimas fuera de rango.
    return round(min(max(total, 0.0), 100.0), 2)
