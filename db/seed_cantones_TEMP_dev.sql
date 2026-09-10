-- ============================================================
-- ATAJO OPCIONAL DE DESARROLLO - NO ES EL SEED DEL PROYECTO
--
-- El eje territorial real ya lo carga el ETL del SNIT:
--     cd etl/snit && python sync_snit.py --capa cantones
-- que trae los 84 cantones con los limites oficiales del IGN (1:5mil) y los
-- codigos contra los que las otras tres fuentes resuelven su canton_id.
--
-- Este archivo existe solo para probar el flujo de punta a punta en local sin
-- esperar esa descarga: inserta 6 cantones con geometrias de relleno (NO son
-- los limites reales) y codigos DEV-0N. Con esos datos el Factor Ambiental y
-- cualquier cruce geografico dan numeros sin sentido, asi que no sirve para la
-- demo ni para el indice.
--
-- Antes de cargar los cantones reales, borrar estas filas:
--     DELETE FROM cantones WHERE codigo_ine LIKE 'DEV-%';
-- ============================================================
INSERT INTO cantones (codigo_ine, nombre, provincia, poblacion, geom) VALUES
('DEV-01', 'San José',    'San José',    350000, ST_GeomFromText('POLYGON((-84.10 9.92, -84.05 9.92, -84.05 9.96, -84.10 9.96, -84.10 9.92))', 4326)),
('DEV-02', 'Curridabat',  'San José',    75000,  ST_GeomFromText('POLYGON((-84.02 9.90, -83.98 9.90, -83.98 9.93, -84.02 9.93, -84.02 9.90))', 4326)),
('DEV-03', 'Alajuela',    'Alajuela',    300000, ST_GeomFromText('POLYGON((-84.24 10.00, -84.18 10.00, -84.18 10.04, -84.24 10.04, -84.24 10.00))', 4326)),
('DEV-04', 'Pococí',      'Limón',       130000, ST_GeomFromText('POLYGON((-83.35 10.30, -83.25 10.30, -83.25 10.40, -83.35 10.40, -83.35 10.30))', 4326)),
('DEV-05', 'Esparza',     'Puntarenas',  35000,  ST_GeomFromText('POLYGON((-84.68 9.95, -84.62 9.95, -84.62 10.00, -84.68 10.00, -84.68 9.95))', 4326)),
('DEV-06', 'Limón',       'Limón',       100000, ST_GeomFromText('POLYGON((-83.05 9.96, -82.98 9.96, -82.98 10.02, -83.05 10.02, -83.05 9.96))', 4326))
ON CONFLICT (codigo_ine) DO NOTHING;
