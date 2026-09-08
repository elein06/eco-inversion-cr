"""
Clasificación de contratos como "ambientales" — Integrante 2.

Este es el punto más discutible de la fuente SICOP y por eso vive en su propio
archivo, con el criterio a la vista.

NO es machine learning. Es una lista de palabras clave agrupadas por categoría
que se busca con una sola expresión regular sobre la descripción del objeto
contractual. Se eligió así a propósito:

  * el criterio se puede leer completo en 60 líneas y defender en la exposición,
  * la misma entrada siempre da la misma salida, y
  * cuando se equivoca, se ve exactamente por qué palabra se equivocó.

La contrapartida es imprecisión: hay falsos positivos (un contrato de
"recolección de residuos electrónicos de oficina" no es un proyecto ambiental)
y falsos negativos (un contrato ambiental descrito con palabras que no están en
la lista). Eso se documenta, no se disimula.

El texto se normaliza sin tildes antes de buscar, así que basta escribir cada
palabra clave una vez y sin tilde: "arborizacion" también encuentra
"arborización" y "ARBORIZACIÓN".
"""
import re
import unicodedata

# Categoría -> palabras clave. La categoría es lo que se guarda en
# `contratos_ambientales.categoria_detectada`, y sirve para que el panel del
# mapa pueda decir de qué tipo de inversión ambiental se trata.
PALABRAS_CLAVE_AMBIENTAL = {
    "residuos": [
        "residuos",
        "desechos",
        "basura",
        "relleno sanitario",
        "recoleccion de desechos",
        "vertedero",
    ],
    "reciclaje": [
        "reciclaje",
        "reciclable",
        "centro de acopio",
        "valorizables",
        "compostaje",
    ],
    "agua": [
        "alcantarillado",
        "tratamiento de aguas",
        "aguas residuales",
        "planta de tratamiento",
        "acueducto",
        "saneamiento",
        "pluvial",
    ],
    "areas_verdes": [
        "arborizacion",
        "reforestacion",
        "areas verdes",
        "parque urbano",
        "vivero",
        "ornato",
        "zonas verdes",
    ],
    "gestion_ambiental": [
        "gestion ambiental",
        "impacto ambiental",
        "plan regulador ambiental",
        "educacion ambiental",
        "estudio ambiental",
        "carbono neutral",
    ],
    "infraestructura_verde": [
        "infraestructura verde",
        "energia solar",
        "paneles solares",
        "movilidad sostenible",
        "ciclovia",
        "eficiencia energetica",
    ],
}

# Orden en que se prueban las categorías. Importa: una descripción puede
# encajar en varias, y se guarda la primera que aparece en este orden. Va de lo
# más específico a lo más genérico, para que "gestion_ambiental" no se coma
# contratos que en realidad son de residuos o de agua.
ORDEN_CATEGORIAS = [
    "residuos",
    "reciclaje",
    "agua",
    "areas_verdes",
    "infraestructura_verde",
    "gestion_ambiental",
]

# Una regex por categoría, sobre texto ya normalizado sin tildes.
# \b en los extremos evita que "agua" encuentre "aguacate" o "paraguas".
_PATRONES = {
    categoria: re.compile(
        r"\b(?:" + "|".join(re.escape(p) for p in palabras) + r")\b",
        re.IGNORECASE,
    )
    for categoria, palabras in PALABRAS_CLAVE_AMBIENTAL.items()
}


def sin_tildes(texto):
    """Quita tildes y diéresis, dejando la letra base. 'residuós' -> 'residuos'."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )


def clasificar(descripcion):
    """
    Devuelve (categoria, palabra_encontrada) o (None, None) si la descripción
    no encaja en ninguna categoría ambiental.
    """
    if descripcion is None:
        return (None, None)
    texto = sin_tildes(descripcion)
    if not texto.strip():
        return (None, None)

    for categoria in ORDEN_CATEGORIAS:
        encontrado = _PATRONES[categoria].search(texto)
        if encontrado:
            return (categoria, encontrado.group(0).lower())
    return (None, None)


def es_ambiental(descripcion):
    return clasificar(descripcion)[0] is not None


def resumen_criterio():
    """
    Texto del criterio, para imprimirlo en la corrida y pegarlo en la
    exposición sin tener que abrir el código.
    """
    lineas = [
        "Criterio de clasificación ambiental (regla explícita, sin ML):",
        "  texto normalizado sin tildes, búsqueda por palabra completa (\\b),",
        "  primera categoría que coincide según este orden de prioridad:",
    ]
    for categoria in ORDEN_CATEGORIAS:
        lineas.append(
            "    {:<22} {}".format(
                categoria, ", ".join(PALABRAS_CLAVE_AMBIENTAL[categoria])
            )
        )
    total = sum(len(v) for v in PALABRAS_CLAVE_AMBIENTAL.values())
    lineas.append(
        "  {} palabras clave en {} categorías.".format(
            total, len(PALABRAS_CLAVE_AMBIENTAL)
        )
    )
    return "\n".join(lineas)
