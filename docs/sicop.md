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

No se usa machine learning. Se define un diccionario de palabras clave que se busca (regex, insensible a mayúsculas) en la descripción del objeto contractual, agrupadas en **6 categorías** — las mismas que usan el panel del frontend (`frontend/src/SICOP/estilos.ts`) y el sub-puntaje de diversidad de la vista `v_factor_inversion` (ver abajo):

```python
PALABRAS_CLAVE_AMBIENTAL = {
    "residuos": ["residuos"],
    "reciclaje": ["reciclaje"],
    "agua": ["alcantarillado", "tratamiento de aguas"],
    "areas_verdes": ["arborizacion", "arborización", "reforestacion", "reforestación"],
    "infraestructura_verde": ["infraestructura verde"],
    "gestion_ambiental": ["gestion ambiental", "gestión ambiental"],
}
```

`categoria_detectada` guarda la **categoría** (una de las 6 claves de arriba), no la palabra que matcheó — así una descripción que dice "reforestación" y otra que dice "arborización" cuentan como la misma categoría (`areas_verdes`) para el sub-puntaje de diversidad.

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
2. Aplicar el filtro de palabras clave sobre `descripcion_objeto` → `categoria_detectada` (una de las 6 categorías de arriba).
3. Vincular cada contrato a un `canton_id` (por nombre de municipalidad, normalizado contra `cantones.nombre`).
4. Insertar en `contratos_ambientales` (ver [db/schema.sql](../db/schema.sql)).
5. Registrar la corrida en `sincronizaciones` (`fuente_id` = SICOP).

## Frecuencia de sincronización

Semanal.

## Riesgo conocido

La clasificación por palabras clave tendrá imprecisión inevitable (falsos positivos/negativos). Se documenta el criterio exacto usado en vez de presentarlo como perfecto.

## Factor de Inversión Municipal — vista y endpoint

`etl/sicop/factor_inversion.py` define `v_factor_inversion`: una vista normal
(no materializada — son sumas y conteos sobre unos miles de filas sin
geometría, se calcula en milisegundos y queda al día sola en cuanto el ETL
inserta contratos nuevos) — misma arquitectura que `v_factor_ambiental`
(SNIT), `v_factor_conectividad` (OSM) y `v_factor_seguridad` (OIJ).
`backend/app/indice.py` solo lee esa vista, no recalcula nada.

Metodología (decisión del equipo, no un indicador oficial): tres
sub-puntajes, porque "inversión municipal ambiental" no es solo plata:

- **Monto (50%)** — plata en contratos ambientales por habitante (o el monto
  absoluto si el cantón no tiene `poblacion` cargada; queda registrado en la
  columna `base_monto`). Solo se suman los contratos en colones: uno que
  quedó en otra moneda porque SICOP no trajo tipo de cambio no se puede sumar
  sin mentir sobre el monto — se cuenta aparte en `contratos_otra_moneda`.
- **Cantidad (30%)** — cuántos contratos ambientales distintos. Un cantón con
  un solo contrato gigante no demuestra el mismo compromiso sostenido que uno
  con varios.
- **Diversidad (20%)** — cuántas de las 6 categorías del clasificador
  aparecen (`categorias / 6`).

Monto y cantidad se normalizan con `PERCENT_RANK` (no min-max) porque el
gasto municipal tiene cola muy larga: un solo contrato de alcantarillado de
miles de millones aplastaría la escala de los otros 83 cantones. Un cantón
sin ningún contrato ambiental queda en 0, no en `NULL`: la ausencia de
inversión municipal ambiental es información, no un dato faltante.

Columnas: `canton_id`, `codigo_ine`, `nombre`, `provincia`, `contratos`,
`contratos_otra_moneda`, `monto_total`, `categorias`, `base_monto`,
`sub_monto`, `sub_cantidad`, `sub_diversidad`, `factor_inversion`. El backend
la expone en:

- `GET /inversion/factor` — los 84 cantones con su desglose;
  `GET /inversion/factor/{canton_id}` para uno solo
- `GET /inversion/resumen` — contratos y montos por categoría (procedencia;
  no depende de la vista, responde aunque no se haya corrido
  `--calcular-factor`)

Si `v_factor_inversion` todavía no existe, `/inversion/factor` responde
`503` con el comando que falta correr — mismo criterio que
`/infraestructura/factor` (OSM) y `/seguridad/factor` (OIJ). Se crea con:

```bash
cd etl/sicop
python sync_sicop.py --calcular-factor
```

(solo, o combinado con una carga: `python sync_sicop.py --archivo
reportes/contratos_2025.xlsx --calcular-factor`).
