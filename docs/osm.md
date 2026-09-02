# Fuente OSINT: OpenStreetMap / Overpass API

**Responsable:** Integrante 3
**Factor del índice:** Factor de Conectividad (25%)

## Qué aporta

Puntos de interés relevantes para conectividad e infraestructura por zona: centros de acopio, escuelas, vías principales.

## Endpoint / forma de consumo

- Protocolo: **Overpass QL** sobre la Overpass API.

  ```
  POST {OVERPASS_API_URL}
  Content-Type: text/plain

  [out:json][timeout:25];
  area["ISO3166-2"="CR-SJ"]->.a;
  (
    node["amenity"="recycling"](area.a);
    node["amenity"="school"](area.a);
    way["highway"~"primary|secondary"](area.a);
  );
  out center;
  ```

- Librerías Python: `overpy` (construcción de la consulta) + `osm2geojson` (conversión del resultado a GeoJSON).

## Formato de respuesta (ejemplo simplificado)

```json
{
  "elements": [
    {
      "type": "node",
      "id": 123456789,
      "lat": 9.9333,
      "lon": -84.0833,
      "tags": { "amenity": "recycling", "name": "Centro de Acopio X" }
    }
  ]
}
```

## Normalización y carga

1. Convertir el resultado de Overpass a GeoJSON con `osm2geojson`.
2. Clasificar cada elemento en una `categoria` normalizada (`centro_acopio`, `escuela`, `via_principal`, ...).
3. Vincular a `canton_id` por intersección espacial (`ST_Contains(cantones.geom, punto)`).
4. Insertar/actualizar en `infraestructura_osm` (ver [db/schema.sql](../db/schema.sql)), con `valido_hasta = now() + 7 days`.
5. Registrar la corrida en `sincronizaciones` (`fuente_id` = OSM).

## Caché obligatoria

Las instancias públicas de Overpass tienen límites de uso estrictos. El backend **nunca** debe volver a consultar Overpass en cada carga del mapa: primero revisa si existen filas en `infraestructura_osm` con `valido_hasta > now()` para el cantón solicitado, y solo si no hay caché vigente dispara una sincronización nueva.

## Frecuencia de sincronización

Caché de 7 días por zona.
