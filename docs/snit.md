# Fuente OSINT: SNIT (Sistema Nacional de Información Territorial)

**Responsable:** Integrante 1
**Factor del índice:** Factor Ambiental (25%)

## Qué aporta

Capas territoriales oficiales: áreas protegidas, corredores biológicos e hidrografía. Se usan para determinar si una zona candidata queda dentro o fuera de un área con restricción ambiental.

## Endpoint / forma de consumo

- Protocolo: **WFS** (Web Feature Service), estándar OGC.
- Paso 1 — `GetCapabilities` contra el nodo SNIT elegido, para confirmar el nombre exacto de las capas disponibles (varía según nodo):

  ```
  GET {SNIT_WFS_BASE_URL}?service=WFS&version=2.0.0&request=GetCapabilities
  ```

- Paso 2 — `GetFeature` filtrando por bounding box o por cantón, salida en GML o GeoJSON:

  ```
  GET {SNIT_WFS_BASE_URL}?service=WFS&version=2.0.0&request=GetFeature
      &typeName=<nombre_capa_confirmado>
      &outputFormat=application/json
      &bbox=<minx,miny,maxx,maxy,EPSG:4326>
  ```

- Librería Python: `owslib.wfs.WebFeatureService`.

## Formato de respuesta (ejemplo simplificado GeoJSON)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[[...]]] },
      "properties": {
        "nombre": "Reserva Forestal ...",
        "categoria": "area_protegida"
      }
    }
  ]
}
```

## Normalización y carga

1. Reproyectar a EPSG:4326 si el nodo devuelve otra proyección.
2. Guardar en `capas_snit` (ver [db/schema.sql](../db/schema.sql)): `tipo_capa`, `geom`, `atributos` (JSONB — absorbe la variabilidad de campos entre nodos).
3. Registrar la corrida en `sincronizaciones` (`fuente_id` = SNIT), con `estado` y `registros_procesados`.

## Frecuencia de sincronización

Semanal, o una sola vez al inicio del proyecto — estas capas casi no cambian.

## Riesgo conocido

La disponibilidad exacta de la capa de corredores biológicos depende del nodo SNIT elegido. Verificar en la semana 1 del cronograma y sustituir por otra capa territorial disponible si no existe.
