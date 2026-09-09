-- ============================================================
-- SOLO PARA DESARROLLO LOCAL — NO ES EL SEED FINAL DEL PROYECTO
--
-- Hallazgo: db/schema.sql crea `cantones` con geom NOT NULL, pero ningun
-- script del repo la puebla todavia (etl/snit/sync_snit.py solo carga
-- `capas_snit`, no `cantones`). Sin esta tabla poblada, get_canton_id_por_nombre()
-- siempre devuelve NULL y CUALQUIER ETL (SICOP, OSM, OIJ) descarta todas sus
-- filas silenciosamente. Esto bloquea a los 4 integrantes, no solo a OIJ.
--
-- Este archivo es un parche temporal con 6 cantones y geometrias de
-- relleno (NO son los limites reales) solo para poder probar el flujo
-- de principio a fin en local. Cuando Integrante 1 cargue los limites
-- reales desde SNIT, este archivo debe eliminarse y las filas reales
-- deben reemplazar estas.
-- ============================================================
INSERT INTO cantones (codigo_ine, nombre, provincia, poblacion, geom) VALUES
('DEV-01', 'San José',    'San José',    350000, ST_GeomFromText('POLYGON((-84.10 9.92, -84.05 9.92, -84.05 9.96, -84.10 9.96, -84.10 9.92))', 4326)),
('DEV-02', 'Curridabat',  'San José',    75000,  ST_GeomFromText('POLYGON((-84.02 9.90, -83.98 9.90, -83.98 9.93, -84.02 9.93, -84.02 9.90))', 4326)),
('DEV-03', 'Alajuela',    'Alajuela',    300000, ST_GeomFromText('POLYGON((-84.24 10.00, -84.18 10.00, -84.18 10.04, -84.24 10.04, -84.24 10.00))', 4326)),
('DEV-04', 'Pococí',      'Limón',       130000, ST_GeomFromText('POLYGON((-83.35 10.30, -83.25 10.30, -83.25 10.40, -83.35 10.40, -83.35 10.30))', 4326)),
('DEV-05', 'Esparza',     'Puntarenas',  35000,  ST_GeomFromText('POLYGON((-84.68 9.95, -84.62 9.95, -84.62 10.00, -84.68 10.00, -84.68 9.95))', 4326)),
('DEV-06', 'Limón',       'Limón',       100000, ST_GeomFromText('POLYGON((-83.05 9.96, -82.98 9.96, -82.98 10.02, -83.05 10.02, -83.05 9.96))', 4326))
ON CONFLICT (codigo_ine) DO NOTHING;
