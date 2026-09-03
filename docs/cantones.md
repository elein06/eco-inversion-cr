# Tabla compartida: `cantones`

No es una fuente OSINT de las cuatro asignadas — es la unidad territorial
que las une a todas. La toma el equipo de OSM (Integrante 3) porque es el
primer bloqueante para probar la carga real de `infraestructura_osm`.

## Fuente de los polígonos

Se descarga manualmente (no hay acceso automatizado a estos dominios desde
el entorno de Claude) uno de estos dos GeoJSON con los 81-84 cantones de
Costa Rica y se guarda en `db/cantones_cr.geojson`:

- ArcGIS Hub (datos abiertos, campos `NOM_PROV` / `NOM_CANT_1`):
  https://daticos-geotec.opendata.arcgis.com/datasets/249bc8711c33493a90b292b55ed3abad_0
- GitHub (campos `NAME_1` / `NAME_2`):
  https://github.com/maufonsecasdfg/costa-rica-geojson/blob/main/costaricacantones.geojson

## Carga

```
python etl/common/load_cantones.py --geojson db/cantones_cr.geojson
```

El script autodetecta el nombre de los campos de provincia/cantón; si falla,
pasarlos con `--prov-field` / `--canton-field` (el mensaje de error lista los
campos disponibles en el archivo).

## Sobre `codigo_ine`

Ninguna de las dos fuentes trae el código oficial INEC/DTA en un campo
identificable. El script genera un código **provisional** determinístico
(`PP-CC`) solo para satisfacer la restricción `UNIQUE NOT NULL` del esquema.
Si alguien consigue la tabla oficial de códigos, se puede pasar
`--codigos-oficiales tabla.csv` (columnas `provincia,canton,codigo_ine`) para
reemplazarlos sin perder las geometrías. Esto se debe mencionar en el README
como una decisión documentada, igual que los pesos del índice.

## Verificación

Después de cargar, contar cuántos cantones quedaron (debería rondar 81-84):

```sql
SELECT provincia, count(*) FROM cantones GROUP BY provincia ORDER BY provincia;
```
