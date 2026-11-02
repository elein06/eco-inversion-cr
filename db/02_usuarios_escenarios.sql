-- ============================================================
-- Eco-Inversión Costa Rica — Usuarios, roles y escenarios privados
--
-- Idempotente: se puede correr sobre una base que ya existe.
--   * Base nueva: docker-compose lo monta como 02_*.sql y Postgres lo
--     ejecuta solo, después de schema.sql.
--   * Base que ya tiene datos (volumen existente): correrlo a mano una vez:
--       docker compose exec -T db psql -U eco_inversion -d eco_inversion_cr \
--           < db/02_usuarios_escenarios.sql
--     En PowerShell (no acepta '<'):
--       cmd /c "docker compose exec -T db psql -U eco_inversion -d eco_inversion_cr < db\02_usuarios_escenarios.sql"
--
-- Roles (ver docs/autenticacion.md):
--   anónimo  -> sin fila aquí; solo lectura de datos públicos
--   usuario  -> gestiona SUS escenarios
--   admin    -> además recalcula el índice. Solo se crea por CLI
--               (python -m app.crear_usuario), nunca por /auth/registro.
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id         SERIAL PRIMARY KEY,
    email              TEXT NOT NULL,
    nombre             TEXT,
    password_hash      TEXT NOT NULL,                       -- argon2id; nunca la contraseña
    rol                VARCHAR(10) NOT NULL DEFAULT 'usuario'
                       CHECK (rol IN ('usuario', 'admin')),
    activo             BOOLEAN NOT NULL DEFAULT TRUE,
    intentos_fallidos  INT NOT NULL DEFAULT 0 CHECK (intentos_fallidos >= 0),
    bloqueado_hasta    TIMESTAMPTZ,
    ultimo_acceso      TIMESTAMPTZ,
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Unicidad sin distinguir mayúsculas: Ana@x.com y ana@x.com son la misma cuenta.
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_email ON usuarios (lower(email));

-- Un escenario es una evaluación privada de un usuario: pesos propios para
-- el índice y una lista corta de cantones. Solo su dueño puede verlo,
-- modificarlo, borrarlo o exportarlo.
CREATE TABLE IF NOT EXISTS escenarios (
    escenario_id    SERIAL PRIMARY KEY,
    usuario_id      INT NOT NULL REFERENCES usuarios(usuario_id) ON DELETE CASCADE,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     VARCHAR(500),
    pesos           JSONB NOT NULL,       -- {"ambiental":..,"inversion":..,"conectividad":..,"seguridad":..}
    cantones        INT[] NOT NULL DEFAULT '{}',   -- vacío = todos los cantones
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_escenarios_usuario ON escenarios(usuario_id);
