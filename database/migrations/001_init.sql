-- =====================================================================
-- Portal SDN Heladería Leche de Cabra - Esquema inicial (PostgreSQL 16)
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS btree_gist; -- EXCLUDE con = y && combinados

-- ---------- Tipos ----------------------------------------------------
CREATE TYPE site_status       AS ENUM ('PROVISIONING','ACTIVE','PROVISION_FAILED',
                                        'DECOMMISSIONING','DECOMMISSION_FAILED','RETIRED');
CREATE TYPE site_size         AS ENUM ('SMALL','MEDIUM');
CREATE TYPE device_role       AS ENUM ('HUB','SPOKE');
CREATE TYPE resource_type     AS ENUM ('SITE_ID','LOOPBACK_V4','UNDERLAY_V4','LAN_V4','LAN_V6',
                                        'TUNNEL1_V4','TUNNEL2_V4','TUNNEL1_V6','TUNNEL2_V6');
CREATE TYPE allocation_status AS ENUM ('RESERVED','ALLOCATED','QUARANTINED','RELEASED');
CREATE TYPE job_type          AS ENUM ('PROVISION','DECOMMISSION','VERIFY','RECONCILE');
CREATE TYPE job_status        AS ENUM ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED');
CREATE TYPE step_status       AS ENUM ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED');

-- ---------- Identidad y acceso --------------------------------------
CREATE TABLE roles (
  id          SMALLSERIAL PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,           -- admin, netops, auditor, viewer
  description TEXT
);

CREATE TABLE permissions (
  id          SMALLSERIAL PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,           -- site:create, site:decommission, job:retry ...
  description TEXT
);

CREATE TABLE role_permissions (
  role_id       SMALLINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id SMALLINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cognito_sub   TEXT NOT NULL UNIQUE,         -- identidad externa (Cognito)
  email         TEXT NOT NULL UNIQUE,
  full_name     TEXT NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  mfa_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (
  user_id UUID     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id SMALLINT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
  PRIMARY KEY (user_id, role_id)
);

-- ---------- Inventario ----------------------------------------------
CREATE TABLE device_templates (
  id              SMALLSERIAL PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,       -- spoke-iol-small, spoke-c8000v-medium
  platform        TEXT NOT NULL,              -- ios / iosxe
  model           TEXT NOT NULL,
  wan_interface   TEXT NOT NULL DEFAULT 'Ethernet0/0',
  lan_interfaces  TEXT[] NOT NULL,            -- {Ethernet0/1} o {Ethernet0/1,Ethernet0/2}
  site_size       site_size NOT NULL,
  ansible_vars    JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sites (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code         TEXT NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9-]{3,16}$'), -- nunca se reutiliza
  name         TEXT NOT NULL,
  site_number  SMALLINT,                      -- ID s; NULL cuando ya fue liberado
  size         site_size NOT NULL DEFAULT 'SMALL',
  status       site_status NOT NULL,
  address      TEXT,
  city         TEXT,
  contact_name TEXT,
  contact_phone TEXT,
  created_by   UUID NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_at TIMESTAMPTZ,
  retired_at   TIMESTAMPTZ,
  version      INTEGER NOT NULL DEFAULT 1     -- bloqueo optimista
);
-- un mismo ID s no puede estar en dos sitios vivos
CREATE UNIQUE INDEX ux_sites_live_number ON sites(site_number)
  WHERE status <> 'RETIRED' AND site_number IS NOT NULL;

CREATE TABLE devices (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id          UUID REFERENCES sites(id) ON DELETE RESTRICT,  -- NULL para hubs
  template_id      SMALLINT REFERENCES device_templates(id),
  hostname         TEXT NOT NULL,
  role             device_role NOT NULL,
  mgmt_address     INET NOT NULL,             -- IP underlay (FVRF INET) por la que llega Ansible
  console_host     TEXT,                      -- host EVE-NG para bootstrap day-0
  console_port     INTEGER,
  serial_number    TEXT,
  os_version       TEXT,
  last_backup_s3   TEXT,                      -- s3://.../running-config
  is_active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  decommissioned_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX ux_devices_live_hostname ON devices(hostname) WHERE is_active;

-- ---------- IPAM ----------------------------------------------------
CREATE TABLE ip_pools (
  id              SMALLSERIAL PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  resource        resource_type NOT NULL,
  cidr            CIDR,                       -- NULL para SITE_ID
  int_min         INTEGER,                    -- rango para SITE_ID (3..N)
  int_max         INTEGER,
  prefix_length   SMALLINT,                   -- tamaño de cada asignación (/32, /24, /64)
  quarantine_days SMALLINT NOT NULL DEFAULT 30,
  description     TEXT,
  CHECK ((resource = 'SITE_ID' AND int_min IS NOT NULL AND int_max IS NOT NULL)
      OR (resource <> 'SITE_ID' AND cidr IS NOT NULL AND prefix_length IS NOT NULL))
);

CREATE TABLE ip_allocations (
  id               BIGSERIAL PRIMARY KEY,
  pool_id          SMALLINT NOT NULL REFERENCES ip_pools(id),
  site_id          UUID NOT NULL REFERENCES sites(id),
  resource         resource_type NOT NULL,
  prefix           CIDR,                      -- valor IP (o NULL si es SITE_ID)
  int_value        INTEGER,                   -- valor numérico (SITE_ID)
  status           allocation_status NOT NULL DEFAULT 'RESERVED',
  reserved_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  allocated_at     TIMESTAMPTZ,
  quarantined_at   TIMESTAMPTZ,
  quarantine_until TIMESTAMPTZ,
  released_at      TIMESTAMPTZ,
  job_id           UUID,                      -- FK diferida (jobs se crea después)
  CHECK ((prefix IS NOT NULL) <> (int_value IS NOT NULL)),
  -- Ningún prefijo vivo se solapa con otro del mismo pool
  EXCLUDE USING gist (pool_id WITH =, prefix inet_ops WITH &&)
    WHERE (status IN ('RESERVED','ALLOCATED','QUARANTINED') AND prefix IS NOT NULL)
);
-- Ningún Site ID vivo duplicado
CREATE UNIQUE INDEX ux_alloc_live_int ON ip_allocations(pool_id, int_value)
  WHERE status IN ('RESERVED','ALLOCATED','QUARANTINED') AND int_value IS NOT NULL;
CREATE INDEX ix_alloc_site ON ip_allocations(site_id);
CREATE INDEX ix_alloc_quarantine ON ip_allocations(quarantine_until) WHERE status = 'QUARANTINED';

-- ---------- Monitoreo ----------------------------------------------
CREATE TABLE zabbix_hosts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id       UUID NOT NULL REFERENCES devices(id),
  zabbix_hostid   TEXT,                       -- id devuelto por la API de Zabbix
  technical_name  TEXT NOT NULL,              -- R7-ANTIGUA
  host_groups     TEXT[] NOT NULL,
  templates       TEXT[] NOT NULL,
  tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
  snmp_address    INET NOT NULL,
  state           TEXT NOT NULL CHECK (state IN ('PENDING','REGISTERED','DRIFT','REMOVED','ERROR')),
  last_sync_at    TIMESTAMPTZ,
  last_error      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  removed_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX ux_zbx_live_device ON zabbix_hosts(device_id) WHERE state <> 'REMOVED';

-- ---------- Automatización -----------------------------------------
CREATE TABLE jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id         UUID NOT NULL REFERENCES sites(id),
  type            job_type NOT NULL,
  status          job_status NOT NULL DEFAULT 'QUEUED',
  requested_by    UUID NOT NULL REFERENCES users(id),
  idempotency_key TEXT UNIQUE,
  parent_job_id   UUID REFERENCES jobs(id),   -- reintentos
  attempt         SMALLINT NOT NULL DEFAULT 1,
  extra_vars_s3   TEXT,                       -- variables renderizadas (sin secretos)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  error_summary   TEXT
);
-- un solo job activo por sitio
CREATE UNIQUE INDEX ux_jobs_one_active_per_site ON jobs(site_id)
  WHERE status IN ('QUEUED','RUNNING');

ALTER TABLE ip_allocations
  ADD CONSTRAINT fk_alloc_job FOREIGN KEY (job_id) REFERENCES jobs(id);

CREATE TABLE ansible_executions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  playbook        TEXT NOT NULL,              -- playbooks/site_provision.yml
  limit_hosts     TEXT NOT NULL,
  tags            TEXT[],
  runner_ref      TEXT,                       -- ARN de la tarea ECS
  image_digest    TEXT NOT NULL,              -- trazabilidad del Execution Environment
  git_sha         TEXT NOT NULL,              -- versión de playbooks
  status          job_status NOT NULL DEFAULT 'QUEUED',
  rc              INTEGER,
  stats           JSONB,                      -- ok/changed/failed/unreachable por host
  log_s3          TEXT,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ
);

CREATE TABLE job_results (
  id              BIGSERIAL PRIMARY KEY,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  execution_id    UUID REFERENCES ansible_executions(id),
  step            TEXT NOT NULL,              -- base, crypto, dmvpn, routing, lan, snmp, zabbix, verify
  step_order      SMALLINT NOT NULL,
  status          step_status NOT NULL,
  changed         BOOLEAN,
  output          JSONB,                      -- resumen estructurado (p. ej. vecinos OSPF)
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  UNIQUE (execution_id, step)
);

-- ---------- Eventos (outbox) y auditoría ---------------------------
CREATE TABLE events (
  id              BIGSERIAL PRIMARY KEY,
  aggregate_type  TEXT NOT NULL,              -- Site, Job, IpPool
  aggregate_id    TEXT NOT NULL,
  event_type      TEXT NOT NULL,              -- SiteProvisioningRequested ...
  payload         JSONB NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at    TIMESTAMPTZ                 -- NULL = pendiente de publicar en SQS
);
CREATE INDEX ix_events_unpublished ON events(id) WHERE published_at IS NULL;

CREATE TABLE audit_logs (
  id              BIGSERIAL PRIMARY KEY,
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_user_id   UUID REFERENCES users(id),
  actor_type      TEXT NOT NULL CHECK (actor_type IN ('USER','SYSTEM','RUNNER')),
  action          TEXT NOT NULL,              -- site.create, site.decommission.confirm ...
  target_type     TEXT NOT NULL,
  target_id       TEXT NOT NULL,
  request_id      TEXT,                       -- correlación con CloudWatch
  source_ip       INET,
  user_agent      TEXT,
  before_state    JSONB,
  after_state     JSONB,
  outcome         TEXT NOT NULL CHECK (outcome IN ('SUCCESS','FAILURE','DENIED')),
  prev_hash       BYTEA,
  row_hash        BYTEA NOT NULL              -- sha256(prev_hash || contenido)
);
CREATE INDEX ix_audit_target ON audit_logs(target_type, target_id);
CREATE INDEX ix_audit_time   ON audit_logs(occurred_at DESC);

-- La bitácora es solo-inserción
CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs es inmutable';
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

-- ---------- Metadatos de secretos (nunca el valor) -----------------
CREATE TABLE secrets_metadata (
  id              SMALLSERIAL PRIMARY KEY,
  logical_name    TEXT NOT NULL UNIQUE,       -- ikev2_psk, router_admin, snmpv3_user, zabbix_api
  secret_arn      TEXT NOT NULL,
  scope           TEXT NOT NULL CHECK (scope IN ('GLOBAL','HUBS','SPOKES','PLATFORM')),
  rotation_days   SMALLINT,
  last_rotated_at TIMESTAMPTZ,
  description     TEXT
);

-- ---------- Datos semilla ------------------------------------------
INSERT INTO roles(name, description) VALUES
 ('admin','Gestión total de la plataforma'),
 ('netops','Alta, baja y reintentos de sitios'),
 ('auditor','Lectura de auditoría e inventario'),
 ('viewer','Solo lectura de inventario');

INSERT INTO permissions(code) VALUES
 ('site:read'),('site:create'),('site:update'),('site:decommission'),
 ('job:read'),('job:retry'),('job:cancel'),('ipam:read'),('ipam:admin'),
 ('audit:read'),('user:admin'),('monitoring:reconcile');

INSERT INTO role_permissions
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin'
   OR (r.name = 'netops'  AND p.code IN ('site:read','site:create','site:update','site:decommission',
                                         'job:read','job:retry','job:cancel','ipam:read','monitoring:reconcile'))
   OR (r.name = 'auditor' AND p.code IN ('site:read','job:read','ipam:read','audit:read'))
   OR (r.name = 'viewer'  AND p.code IN ('site:read','job:read','ipam:read'));

-- Pools del equipo: D = 28, MM = 12 (MMDD = 1228).
-- Túneles: 192.168.5.0/25 (Hub 1, router s = .s) y 192.168.5.128/25 (Hub 2, router s = .130+s).
-- Máximo Site ID = min(253 - D, 254 - 130) = min(225, 124) = 124 (lo limita la nube del Hub 2)
INSERT INTO ip_pools(name, resource, int_min, int_max, quarantine_days, description) VALUES
 ('site-ids','SITE_ID',3,124,30,'ID s de sitio; 1-2 reservados para hubs; max = min(253 - D, 124)');
INSERT INTO ip_pools(name, resource, cidr, prefix_length, quarantine_days) VALUES
 ('loopbacks','LOOPBACK_V4','10.254.0.0/24',32,30),
 ('underlay','UNDERLAY_V4','172.16.0.0/24',32,0),
 ('lan-v4','LAN_V4','10.0.0.0/8',24,30),
 ('lan-v6','LAN_V6','2001:1228::/32',64,30),
 ('tunnel1-v4','TUNNEL1_V4','192.168.5.0/25',32,30),
 ('tunnel2-v4','TUNNEL2_V4','192.168.5.128/25',32,30),
 ('tunnel1-v6','TUNNEL1_V6','fd00:5::/64',128,30),
 ('tunnel2-v6','TUNNEL2_V6','fd00:5:1::/64',128,30);
