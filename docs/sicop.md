# Fuente OSINT: SICOP (Sistema Integrado de Compras Públicas)

**Responsable:** Integrante 2
**Factor del índice:** Factor de Inversión Municipal (25%)

## Qué aporta

Contratos públicos municipales relacionados con gestión ambiental, usados como proxy de apoyo institucional a un cantón.

## Endpoint / forma de consumo

SICOP no ofrece una API REST limpia. La fuente son reportes descargables (Excel/CSV/JSON) desde su módulo de datos abiertos:

```
{SICOP_DATOS_ABIERTOS_URL}
```

Se descarga el reporte de contratos por período y se procesa localmente con `pandas` + `openpyxl`.

## Criterio de clasificación "ambiental"

No se usa machine learning. Se define una lista de palabras clave que se busca (regex, insensible a mayúsculas) en la descripción del objeto contractual:

```python
PALABRAS_CLAVE_AMBIENTAL = [
    "residuos", "reciclaje", "arborizacion", "arborización",
    "alcantarillado", "gestion ambiental", "gestión ambiental",
    "infraestructura verde", "tratamiento de aguas", "reforestacion",
    "reforestación",
]
```

Este criterio es simple e imperfecto a propósito: se documenta como regla explícita (no como IA) para poder justificarlo en la exposición.

## Formato de datos (columnas esperadas del reporte)

| Columna origen         | Campo normalizado      |
|-------------------------|-------------------------|
| Institución              | `institucion`           |
| Cédula/Municipalidad     | `municipalidad`         |
| Monto adjudicado         | `monto`                 |
| Moneda                   | `moneda`                |
| Fecha de contrato        | `fecha_contrato`         |
| Descripción del objeto   | `descripcion_objeto`    |

## Normalización y carga

1. Leer el archivo descargado con `pandas.read_excel` / `read_csv`.
2. Aplicar el filtro de palabras clave sobre `descripcion_objeto` → `categoria_detectada`.
3. Vincular cada contrato a un `canton_id` (por nombre de municipalidad, normalizado contra `cantones.nombre`).
4. Insertar en `contratos_ambientales` (ver [db/schema.sql](../db/schema.sql)).
5. Registrar la corrida en `sincronizaciones` (`fuente_id` = SICOP).

## Frecuencia de sincronización

Semanal.

## Riesgo conocido

La clasificación por palabras clave tendrá imprecisión inevitable (falsos positivos/negativos). Se documenta el criterio exacto usado en vez de presentarlo como perfecto.
