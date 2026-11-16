-- =====================================================================
-- 003 - Conectividad de las sucursales
--   * El worker hace ping a cada router cada minuto y guarda el resultado aquí
--   * Una sucursal sin respuesta por más de N minutos se pregunta al administrador
--   * FORGET: retiro de un router que ya no existe (no se conecta a él)
-- =====================================================================
ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'FORGET';

CREATE TABLE site_health (
  site_id              UUID PRIMARY KEY REFERENCES sites(id) ON DELETE CASCADE,
  state                TEXT NOT NULL CHECK (state IN ('REACHABLE','UNREACHABLE')),
  since                TIMESTAMPTZ NOT NULL,      -- desde cuándo está en este estado
  checked_at           TIMESTAMPTZ NOT NULL,      -- última prueba
  failures             SMALLINT NOT NULL DEFAULT 0,
  first_failure_at     TIMESTAMPTZ,               -- primera prueba fallida de la racha
  prompt_snoozed_until TIMESTAMPTZ                -- "sigue en servicio": no volver a preguntar antes
);

INSERT INTO permissions(code, description) VALUES
  ('site:forget', 'Retirar una sucursal cuyo router ya no responde');
INSERT INTO role_permissions
SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'admin' AND p.code = 'site:forget';
