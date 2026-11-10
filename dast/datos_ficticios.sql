-- ============================================================
-- Datos FICTICIOS para el análisis DAST (ítem 4.7, ver docs/dast.md)
--
-- Se carga solo en la base desechable del ambiente DAST, después de
-- db/schema.sql y db/02_usuarios_escenarios.sql. No son cantones reales:
-- códigos DAST-0N y geometrías de relleno, igual que los de las pruebas
-- de API. Las cuentas NO se crean aquí: ejecutar_dast.py las registra por
-- POST /auth/registro (el flujo real) con una contraseña aleatoria.
-- ============================================================
INSERT INTO cantones (codigo_ine, nombre, provincia, poblacion, geom) VALUES
('DAST-01', 'Cantón Alfa', 'San José', 1000,
 ST_Multi(ST_MakeEnvelope(-84.10, 9.90, -84.05, 9.95, 4326))),
('DAST-02', 'Cantón Beta', 'Alajuela', 1000,
 ST_Multi(ST_MakeEnvelope(-84.25, 10.00, -84.20, 10.05, 4326))),
('DAST-03', 'Cantón Gamma', 'Cartago', 1000,
 ST_Multi(ST_MakeEnvelope(-83.95, 9.85, -83.90, 9.90, 4326)));

INSERT INTO indice_viabilidad
    (canton_id, factor_ambiental, factor_inversion, factor_conectividad,
     factor_seguridad, indice_total, pesos_usados)
SELECT canton_id, 80, 40, 60, 20, 50,
       '{"ambiental":0.25,"inversion":0.25,"conectividad":0.25,"seguridad":0.25}'
FROM cantones WHERE codigo_ine LIKE 'DAST-%';
