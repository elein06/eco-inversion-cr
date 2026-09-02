# Fuente OSINT: Poder Judicial / OIJ — Estadísticas Policiales

**Responsable:** Integrante 4
**Factor del índice:** Factor de Seguridad (25%)
**Nota:** reemplaza a la fuente original del BCCR (evita el trámite de token del servicio SOAP y añade una dimensión de seguridad alineada con el curso).

## Qué aporta

Estadísticas policiales agregadas por cantón y año, usadas como proxy (inverso) de seguridad para el índice de viabilidad.

## Endpoint / forma de consumo

Portal de Datos Abiertos del Poder Judicial, construido sobre **CKAN**. No requiere token.

- Dataset: `estadisticas-policiales`

  ```
  {OIJ_CKAN_BASE_URL}/dataset/estadisticas-policiales
  ```

- Recursos disponibles: CSV, XLS/XLSX, XML, RDF — se descarga el recurso directamente.
- Alternativa vía API (si el recurso está en el datastore de CKAN):

  ```
  GET {OIJ_CKAN_BASE_URL}/api/3/action/datastore_search?resource_id=<id_recurso>&limit=1000
  ```

## Formato de respuesta (ejemplo API CKAN)

```json
{
  "success": true,
  "result": {
    "records": [
      { "Canton": "San José", "Delito": "Robo", "Cantidad": 1200, "Anio": 2024 }
    ]
  }
}
```

## Normalización y carga

1. Descargar el recurso (CSV/XLSX) o consultar `datastore_search`.
2. Limpiar con `pandas`: normalizar nombre de cantón contra `cantones.nombre`, tipo de delito, año.
3. Calcular una tasa normalizada por cantón (ej. delitos por 10,000 habitantes usando `cantones.poblacion`, o un score relativo entre cantones si no se quiere depender de datos de población).
4. Insertar en `estadisticas_seguridad` (ver [db/schema.sql](../db/schema.sql)): `canton_id`, `tipo_delito`, `cantidad`, `anio`.
5. Registrar la corrida en `sincronizaciones` (`fuente_id` = OIJ).

## Advertencia ética (obligatoria en el sistema)

Estas son **estadísticas agregadas por cantón**, nunca a nivel de persona. El sistema nunca debe insinuar que un cantón "peligroso" implica algo sobre sus habitantes, y la correlación entre seguridad e índice de viabilidad **no debe presentarse como causalidad**. Esta advertencia debe ser visible también en el frontend, cerca del Factor de Seguridad.

## Frecuencia de sincronización

Trimestral — estos datasets no se actualizan con mucha frecuencia. El equipo debe fijar desde el inicio un año o rango de años de referencia (`OIJ_ANIO_REFERENCIA`) para mantener consistencia en todo el sistema, ya que los recursos del OIJ pueden tener periodicidad distinta entre sí.
