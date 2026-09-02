-- ============================================================
-- Eco-Inversión Costa Rica — Esquema de base de datos
-- PostgreSQL + PostGIS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ------------------------------------------------------------
-- 1. Catálogo de fuentes OSINT (trazabilidad de procedencia)
-- ------------------------------------------------------------
CREATE TABLE fuentes (
    fuente_id                 SERIAL PRIMARY KEY,
    codigo                    VARCHAR(20) UNIQUE NOT NULL,   -- 'SNIT','SICOP','OSM','OIJ'
    nombre                    TEXT NOT NULL,
    url_oficial               TEXT NOT NULL,
    responsable               TEXT NOT NULL,                 -- integrante a cargo
    tipo_consumo              TEXT NOT NULL,                 -- 'WFS','CKAN/CSV','Overpass API'
    frecuencia_sincronizacion TEXT NOT NULL                  -- 'semanal','trimestral','cache 7 días'
);

-- ------------------------------------------------------------
-- 2. Log de sincronización (manejo de errores + auditoría)
-- ------------------------------------------------------------
CREATE TABLE sincronizaciones (
    sincronizacion_id     SERIAL PRIMARY KEY,
    fuente_id             INT NOT NULL REFERENCES fuentes(fuente_id),
    fecha_ejecucion       TIMESTAMPTZ NOT NULL DEFAULT now(),
    estado                VARCHAR(10) NOT NULL CHECK (estado IN ('exito','error','parcial')),
    registros_procesados  INT,
    mensaje               TEXT
);
CREATE INDEX idx_sync_fuente_fecha ON sincronizaciones(fuente_id, fecha_ejecucion DESC);

-- ------------------------------------------------------------
-- 3. Cantones (unidad territorial común — eje del sistema)
-- ------------------------------------------------------------
CREATE TABLE cantones (
    canton_id     SERIAL PRIMARY KEY,
    codigo_ine    VARCHAR(10) UNIQUE NOT NULL,
    nombre        TEXT NOT NULL,
    provincia     TEXT NOT NULL,
    poblacion     INT,                                       -- dato de referencia (INEC), para normalizar tasas
    geom          GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX idx_cantones_geom ON cantones USING GIST(geom);

-- ------------------------------------------------------------
-- 4. SNIT — capas territoriales
-- ------------------------------------------------------------
CREATE TABLE capas_snit (
    capa_id         SERIAL PRIMARY KEY,
    fuente_id       INT NOT NULL REFERENCES fuentes(fuente_id),
    canton_id       INT REFERENCES cantones(canton_id),      -- nullable: una geometría puede cruzar cantones
    tipo_capa       VARCHAR(50) NOT NULL,                    -- 'area_protegida','corredor_biologico','hidrografia'
    nombre          TEXT,
    geom            GEOMETRY(Geometry, 4326) NOT NULL,
    atributos       JSONB,                                   -- flexible: los atributos varían según el nodo WFS
    fecha_consulta  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_capas_snit_geom   ON capas_snit USING GIST(geom);
CREATE INDEX idx_capas_snit_canton ON capas_snit(canton_id);
CREATE INDEX idx_capas_snit_tipo   ON capas_snit(tipo_capa);

-- ------------------------------------------------------------
-- 5. SICOP — contratos ambientales
-- ------------------------------------------------------------
CREATE TABLE contratos_ambientales (
    contrato_id          SERIAL PRIMARY KEY,
    fuente_id            INT NOT NULL REFERENCES fuentes(fuente_id),
    canton_id            INT REFERENCES cantones(canton_id),
    institucion          TEXT NOT NULL,
    municipalidad        TEXT,
    monto                NUMERIC(18,2) NOT NULL,
    moneda               VARCHAR(3) NOT NULL DEFAULT 'CRC',
    fecha_contrato       DATE,
    descripcion_objeto   TEXT,
    categoria_detectada  TEXT NOT NULL,                      -- palabra clave que matcheó vía regex
    fecha_consulta       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_contratos_canton    ON contratos_ambientales(canton_id);
CREATE INDEX idx_contratos_categoria ON contratos_ambientales(categoria_detectada);

-- ------------------------------------------------------------
-- 6. OSM / Overpass — infraestructura y POIs (con caché de 7 días)
-- ------------------------------------------------------------
CREATE TABLE infraestructura_osm (
    poi_id          SERIAL PRIMARY KEY,
    fuente_id       INT NOT NULL REFERENCES fuentes(fuente_id),
    canton_id       INT REFERENCES cantones(canton_id),
    osm_id          BIGINT NOT NULL,
    osm_tipo        VARCHAR(10) NOT NULL,                    -- 'node','way','relation'
    categoria       VARCHAR(50) NOT NULL,                    -- 'centro_acopio','escuela','via_principal'
    nombre          TEXT,
    geom            GEOMETRY(Geometry, 4326) NOT NULL,
    fecha_consulta  TIMESTAMPTZ NOT NULL DEFAULT now(),
    valido_hasta    TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    UNIQUE(osm_id, osm_tipo)
);
CREATE INDEX idx_osm_geom         ON infraestructura_osm USING GIST(geom);
CREATE INDEX idx_osm_canton       ON infraestructura_osm(canton_id);
CREATE INDEX idx_osm_valido_hasta ON infraestructura_osm(valido_hasta);

-- ------------------------------------------------------------
-- 7. Poder Judicial / OIJ — estadísticas de seguridad (agregadas)
--    Nunca a nivel de persona: solo cantón + tipo de delito + año.
-- ------------------------------------------------------------
CREATE TABLE estadisticas_seguridad (
    estadistica_id  SERIAL PRIMARY KEY,
    fuente_id       INT NOT NULL REFERENCES fuentes(fuente_id),
    canton_id       INT NOT NULL REFERENCES cantones(canton_id),
    tipo_delito     TEXT NOT NULL,
    cantidad        INT NOT NULL CHECK (cantidad >= 0),
    anio            INT NOT NULL,
    fecha_consulta  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(canton_id, tipo_delito, anio)
);
CREATE INDEX idx_seguridad_canton_anio ON estadisticas_seguridad(canton_id, anio);

-- ------------------------------------------------------------
-- 8. Índice de viabilidad — resultado materializado y recalculable
--    Los pesos quedan documentados en pesos_usados, no hardcodeados.
-- ------------------------------------------------------------
CREATE TABLE indice_viabilidad (
    canton_id            INT PRIMARY KEY REFERENCES cantones(canton_id),
    factor_ambiental     NUMERIC(5,2) NOT NULL,
    factor_inversion     NUMERIC(5,2) NOT NULL,
    factor_conectividad  NUMERIC(5,2) NOT NULL,
    factor_seguridad     NUMERIC(5,2) NOT NULL,
    indice_total         NUMERIC(5,2) NOT NULL,
    pesos_usados         JSONB NOT NULL,           -- ej: {"ambiental":0.25,"inversion":0.25,"conectividad":0.25,"seguridad":0.25}
    fecha_calculo        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- Datos semilla mínimos de la tabla fuentes (ajustar responsables reales)
-- ------------------------------------------------------------
INSERT INTO fuentes (codigo, nombre, url_oficial, responsable, tipo_consumo, frecuencia_sincronizacion) VALUES
('SNIT', 'Sistema Nacional de Información Territorial', 'https://www.snitcr.go.cr/ico_servicios_ogc', 'Integrante 1', 'WFS (GetFeature)', 'semanal / una vez'),
('SICOP', 'Datos Abiertos de Contratación Pública', 'https://www.sicop.go.cr/moduloPcont/pcont/rp/CE_MOD_DATOSABIERTOSVIEW.jsp', 'Integrante 2', 'Descarga CSV/Excel/JSON', 'semanal'),
('OSM', 'OpenStreetMap / Overpass API', 'https://wiki.openstreetmap.org/wiki/Overpass_API', 'Integrante 3', 'Overpass QL', 'cache 7 días'),
('OIJ', 'Poder Judicial / OIJ — Estadísticas Policiales', 'https://datosabiertospj.poder-judicial.go.cr/dataset/estadisticas-policiales', 'Integrante 4', 'CKAN (CSV/XML/RDF)', 'trimestral');

-- ------------------------------------------------------------
-- Ejemplo de consulta espacial habilitada por PostGIS
-- (zonas fuera de cualquier área protegida — Factor Ambiental)
-- ------------------------------------------------------------
-- SELECT c.canton_id, c.nombre
-- FROM cantones c
-- WHERE NOT EXISTS (
--     SELECT 1 FROM capas_snit s
--     WHERE s.tipo_capa = 'area_protegida'
--     AND ST_Intersects(c.geom, s.geom)
-- );
