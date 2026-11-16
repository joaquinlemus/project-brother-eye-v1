-- =====================================================================
-- 002 - Portal en la EC2 del laboratorio
--   * Usuarios locales (contraseña Argon2 + MFA TOTP) en lugar de Cognito
--   * Sitios importados/protegidos (R3 y R4 se configuraron a mano: nunca se dan de baja)
--   * Datos de ejecución local (log en disco, sin S3 ni ECS)
--   * Cuarentena corta para el laboratorio (se puede liberar antes desde el portal)
-- =====================================================================

-- ---------- Usuarios locales ----------------------------------------
ALTER TABLE users ALTER COLUMN cognito_sub DROP NOT NULL;
ALTER TABLE users
  ADD COLUMN username        TEXT UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,32}$'),
  ADD COLUMN password_hash   TEXT,                       -- Argon2id
  ADD COLUMN mfa_secret_enc  TEXT,                       -- secreto TOTP cifrado (Fernet)
  ADD COLUMN mfa_last_step   BIGINT,                     -- evita reutilizar un código TOTP
  ADD COLUMN failed_logins   SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN locked_until    TIMESTAMPTZ,
  ADD COLUMN password_changed_at TIMESTAMPTZ;

-- Usuario técnico para acciones del worker e importaciones (no puede iniciar sesión)
INSERT INTO users(id, email, full_name, username, is_active)
VALUES ('00000000-0000-0000-0000-000000000000', 'system@portal.local', 'Sistema', 'system', FALSE);

INSERT INTO permissions(code, description) VALUES
  ('ipam:release', 'Liberar cuarentena antes de tiempo');
INSERT INTO role_permissions
SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'admin' AND p.code = 'ipam:release';

UPDATE roles SET description = 'Administrador: todo, incluidos usuarios'      WHERE name = 'admin';
UPDATE roles SET description = 'Operador de red: altas, bajas y reintentos'   WHERE name = 'netops';
UPDATE roles SET description = 'Auditor: lectura de inventario y auditoría'   WHERE name = 'auditor';
UPDATE roles SET description = 'Lector: solo inventario'                      WHERE name = 'viewer';

-- ---------- Sitios ---------------------------------------------------
ALTER TABLE sites
  ADD COLUMN protected BOOLEAN NOT NULL DEFAULT FALSE,   -- el portal no permite darlo de baja
  ADD COLUMN imported  BOOLEAN NOT NULL DEFAULT FALSE,   -- existía antes del portal
  ADD COLUMN notes     TEXT;

-- ---------- Ejecución local ------------------------------------------
ALTER TABLE jobs ADD COLUMN log_path TEXT;
ALTER TABLE ansible_executions ALTER COLUMN image_digest SET DEFAULT 'ec2-venv';
ALTER TABLE ansible_executions ALTER COLUMN git_sha      SET DEFAULT 'local';

-- ---------- Inventario base ------------------------------------------
INSERT INTO device_templates(name, platform, model, lan_interfaces, site_size) VALUES
  ('spoke-iol-small', 'ios', 'IOL 15.7(3)M2', '{Ethernet0/1}', 'SMALL');

INSERT INTO devices(hostname, role, mgmt_address, os_version) VALUES
  ('R1', 'HUB', '172.16.0.1', 'IOL 15.7(3)M2'),
  ('R2', 'HUB', '172.16.0.2', 'IOL 15.7(3)M2');

-- ---------- Cuarentena de laboratorio ---------------------------------
-- Producción: 30 días. En el laboratorio solo hay R5 y R6 para pruebas: 1 día, y el
-- administrador puede liberarla antes desde el portal (queda en auditoría).
UPDATE ip_pools SET quarantine_days = 1 WHERE quarantine_days > 0;

-- ---------- Control de migraciones ------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
