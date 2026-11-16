"""Adaptadores PostgreSQL. Cada repositorio trabaja sobre la conexión de la transacción actual.

Las reglas de negocio viven en app/domain; aquí solo hay SQL. Las garantías finales de
integridad (IDs y prefijos sin duplicar, un job activo por sitio, auditoría inmutable) las
imponen restricciones de la base de datos (database/migrations/001_init.sql).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from psycopg import Connection, errors

from app.domain.errors import ConcurrencyError, DomainError
from app.domain.ipam.addressing import SiteAddressing
from app.domain.site.model import Site, SiteCode, SiteStatus

SYSTEM_USER = UUID("00000000-0000-0000-0000-000000000000")


# ----------------------------------------------------------------------------- sitios
class SiteRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    @staticmethod
    def to_domain(r: dict) -> Site:
        s = Site(code=SiteCode(r["code"]), name=r["name"], site_number=r["site_number"],
                 created_by=r["created_by"], id=r["id"], status=SiteStatus(r["status"]),
                 activated_at=r["activated_at"], retired_at=r["retired_at"], version=r["version"])
        s.loaded_version = r["version"]  # type: ignore[attr-defined]
        return s

    def get_row(self, site_id: UUID, lock: bool = False) -> dict | None:
        sql = "SELECT * FROM sites WHERE id = %s" + (" FOR UPDATE" if lock else "")
        return self.c.execute(sql, (site_id,)).fetchone()

    def get(self, site_id: UUID, lock: bool = False) -> Site | None:
        r = self.get_row(site_id, lock)
        return self.to_domain(r) if r else None

    def code_exists(self, code: str) -> bool:
        return self.c.execute("SELECT 1 FROM sites WHERE code = %s", (code,)).fetchone() is not None

    def add(self, site: Site, *, protected: bool = False, imported: bool = False,
            notes: str | None = None) -> None:
        self.c.execute(
            """INSERT INTO sites(id, code, name, site_number, size, status, created_by,
                                 activated_at, protected, imported, notes)
               VALUES (%s,%s,%s,%s,'SMALL',%s,%s,%s,%s,%s,%s)""",
            (site.id, site.code.value, site.name, site.site_number, site.status.value,
             site.created_by, site.activated_at, protected, imported, notes))

    def save(self, site: Site) -> None:
        cur = self.c.execute(
            """UPDATE sites SET status=%s, activated_at=%s, retired_at=%s, version=%s
               WHERE id=%s AND version=%s""",
            (site.status.value, site.activated_at, site.retired_at, site.version, site.id,
             site.loaded_version))  # type: ignore[attr-defined]
        if cur.rowcount != 1:
            raise ConcurrencyError("El sitio cambió mientras se procesaba; recarga e intenta de nuevo")
        site.loaded_version = site.version  # type: ignore[attr-defined]

    def list(self, status: str | None = None) -> list[dict]:
        where, args = ("WHERE s.status = %s", [status]) if status else ("", [])
        return self.c.execute(f"""
            SELECT s.*, u.username AS created_by_username,
                   j.id AS last_job_id, j.type AS last_job_type, j.status AS last_job_status,
                   h.state AS health_state, h.since AS health_since, h.checked_at AS health_checked_at
            FROM sites s
            JOIN users u ON u.id = s.created_by
            LEFT JOIN site_health h ON h.site_id = s.id
            LEFT JOIN LATERAL (SELECT id, type, status FROM jobs WHERE site_id = s.id
                               ORDER BY created_at DESC LIMIT 1) j ON TRUE
            {where}
            ORDER BY (s.status = 'RETIRED'), s.site_number, s.created_at""", args).fetchall()

    def counts(self) -> dict[str, int]:
        rows = self.c.execute("SELECT status, count(*) AS n FROM sites GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}


# ----------------------------------------------------------------------------- IPAM
_RESOURCES = [  # (pool, resource, atributo de SiteAddressing, prefijo)
    ("loopbacks", "LOOPBACK_V4", "loopback0", 32),
    ("underlay", "UNDERLAY_V4", "underlay", 32),
    ("lan-v4", "LAN_V4", "lan_v4", 24),
    ("lan-v6", "LAN_V6", "lan_v6", 64),
    ("tunnel1-v4", "TUNNEL1_V4", "tunnel1_v4", 32),
    ("tunnel2-v4", "TUNNEL2_V4", "tunnel2_v4", 32),
    ("tunnel1-v6", "TUNNEL1_V6", "tunnel1_v6", 128),
    ("tunnel2-v6", "TUNNEL2_V6", "tunnel2_v6", 128),
]


def _as_prefix(value, plen: int) -> str:
    if isinstance(value, list):
        value = value[0]
    ip = getattr(value, "ip", None) or value.network_address
    return f"{ip}/{plen}"


class IpamRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def lock(self) -> None:
        # Serializa las altas: dos operadores no pueden obtener el mismo ID a la vez
        self.c.execute("SELECT pg_advisory_xact_lock(1228)")

    def release_expired(self) -> int:
        cur = self.c.execute("""UPDATE ip_allocations SET status='RELEASED', released_at=now()
                                WHERE status='QUARANTINED' AND quarantine_until <= now()""")
        return cur.rowcount

    def site_id_pool(self) -> dict:
        return self.c.execute("SELECT * FROM ip_pools WHERE name='site-ids'").fetchone()

    def used_site_ids(self) -> dict[int, dict]:
        rows = self.c.execute("""
            SELECT a.int_value, a.status, a.quarantine_until, s.code, s.name
            FROM ip_allocations a JOIN sites s ON s.id = a.site_id
            WHERE a.resource='SITE_ID' AND a.status IN ('RESERVED','ALLOCATED','QUARANTINED')
        """).fetchall()
        return {r["int_value"]: r for r in rows}

    def reserve(self, site_id: UUID, addr: SiteAddressing, job_id: UUID) -> None:
        pools = {r["name"]: r["id"] for r in self.c.execute("SELECT id, name FROM ip_pools")}
        try:
            with self.c.transaction():   # savepoint
                self.c.execute("""INSERT INTO ip_allocations(pool_id, site_id, resource, int_value,
                                                             job_id)
                                  VALUES (%s,%s,'SITE_ID',%s,%s)""",
                               (pools["site-ids"], site_id, addr.site_id, job_id))
                for pool, res, attr, plen in _RESOURCES:
                    self.c.execute("""INSERT INTO ip_allocations(pool_id, site_id, resource, prefix,
                                                                 job_id)
                                      VALUES (%s,%s,%s,%s,%s)""",
                                   (pools[pool], site_id, res,
                                    _as_prefix(getattr(addr, attr), plen), job_id))
        except (errors.ExclusionViolation, errors.UniqueViolation) as exc:
            raise DomainError("Recurso IP ya asignado o en cuarentena (restricción de la BD)") from exc

    def allocate(self, site_id: UUID) -> None:
        self.c.execute("""UPDATE ip_allocations SET status='ALLOCATED', allocated_at=now()
                          WHERE site_id=%s AND status='RESERVED'""", (site_id,))

    def quarantine(self, site_id: UUID) -> None:
        self.c.execute("""
            UPDATE ip_allocations a SET status='QUARANTINED', quarantined_at=now(),
                   quarantine_until = now() + make_interval(days => p.quarantine_days)
            FROM ip_pools p
            WHERE p.id = a.pool_id AND a.site_id=%s AND a.status IN ('RESERVED','ALLOCATED')""",
                       (site_id,))

    def release_now(self, site_id: UUID) -> int:
        cur = self.c.execute("""UPDATE ip_allocations SET status='RELEASED', released_at=now()
                                WHERE site_id=%s AND status='QUARANTINED'""", (site_id,))
        return cur.rowcount

    def for_site(self, site_id: UUID) -> list[dict]:
        return self.c.execute("""
            SELECT a.id, p.name AS pool, a.resource, host(a.prefix) AS ip,
                   a.prefix::text AS prefix, a.int_value, a.status, a.reserved_at,
                   a.allocated_at, a.quarantine_until, a.released_at
            FROM ip_allocations a JOIN ip_pools p ON p.id=a.pool_id
            WHERE a.site_id=%s ORDER BY a.id""", (site_id,)).fetchall()

    def list(self, status: str | None, limit: int, offset: int) -> list[dict]:
        where, args = ("WHERE a.status = %s", [status]) if status else ("", [])
        return self.c.execute(f"""
            SELECT a.id, p.name AS pool, a.resource, a.prefix::text AS prefix, a.int_value,
                   a.status, a.reserved_at, a.quarantine_until, a.released_at,
                   s.id AS site_id, s.code AS site_code, s.name AS site_name
            FROM ip_allocations a JOIN ip_pools p ON p.id=a.pool_id JOIN sites s ON s.id=a.site_id
            {where} ORDER BY a.id DESC LIMIT %s OFFSET %s""", [*args, limit, offset]).fetchall()

    def pools_usage(self) -> list[dict]:
        return self.c.execute("""
            SELECT p.id, p.name, p.resource, p.cidr::text AS cidr, p.int_min, p.int_max,
                   p.prefix_length, p.quarantine_days,
                   count(a.*) FILTER (WHERE a.status='RESERVED')    AS reserved,
                   count(a.*) FILTER (WHERE a.status='ALLOCATED')   AS allocated,
                   count(a.*) FILTER (WHERE a.status='QUARANTINED') AS quarantined,
                   count(a.*) FILTER (WHERE a.status='RELEASED')    AS released
            FROM ip_pools p LEFT JOIN ip_allocations a ON a.pool_id=p.id
            GROUP BY p.id ORDER BY p.id""").fetchall()


# ----------------------------------------------------------------------------- jobs
class JobRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def create(self, site_id: UUID, job_type: str, requested_by: UUID,
               parent_job_id: UUID | None = None, attempt: int = 1) -> UUID:
        try:
            with self.c.transaction():   # savepoint
                r = self.c.execute("""INSERT INTO jobs(site_id, type, requested_by, parent_job_id,
                                                       attempt)
                                      VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                                   (site_id, job_type, requested_by, parent_job_id, attempt)).fetchone()
        except errors.UniqueViolation as exc:
            raise DomainError("La sucursal ya tiene un trabajo en curso") from exc
        return r["id"]

    def get(self, job_id: UUID) -> dict | None:
        return self.c.execute("""
            SELECT j.*, s.code AS site_code, s.name AS site_name, s.site_number,
                   s.status AS site_status, u.username AS requested_by_username
            FROM jobs j JOIN sites s ON s.id=j.site_id JOIN users u ON u.id=j.requested_by
            WHERE j.id=%s""", (job_id,)).fetchone()

    def latest_for_site(self, site_id: UUID) -> dict | None:
        return self.c.execute("SELECT * FROM jobs WHERE site_id=%s ORDER BY created_at DESC LIMIT 1",
                              (site_id,)).fetchone()

    def list(self, site_id: UUID | None, status: str | None, limit: int, offset: int) -> list[dict]:
        conds, args = [], []
        if site_id:
            conds.append("j.site_id = %s")
            args.append(site_id)
        if status:
            conds.append("j.status = %s")
            args.append(status)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return self.c.execute(f"""
            SELECT j.id, j.type, j.status, j.attempt, j.created_at, j.started_at, j.finished_at,
                   j.error_summary, j.parent_job_id, s.id AS site_id, s.code AS site_code,
                   s.name AS site_name, s.site_number, u.username AS requested_by_username
            FROM jobs j JOIN sites s ON s.id=j.site_id JOIN users u ON u.id=j.requested_by
            {where} ORDER BY j.created_at DESC LIMIT %s OFFSET %s""",
                              [*args, limit, offset]).fetchall()

    # --- usados por el worker ---
    def claim_next(self) -> dict | None:
        return self.c.execute("""
            SELECT j.*, s.site_number FROM jobs j JOIN sites s ON s.id=j.site_id
            WHERE j.status='QUEUED' ORDER BY j.created_at
            FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()

    def mark_running(self, job_id: UUID, log_path: str) -> None:
        self.c.execute("UPDATE jobs SET status='RUNNING', started_at=now(), log_path=%s WHERE id=%s",
                       (log_path, job_id))

    def finish(self, job_id: UUID, status: str, error: str | None = None) -> None:
        self.c.execute("""UPDATE jobs SET status=%s, finished_at=now(), error_summary=%s
                          WHERE id=%s""", (status, error, job_id))

    def orphaned(self) -> list[dict]:
        return self.c.execute("SELECT * FROM jobs WHERE status='RUNNING' FOR UPDATE").fetchall()

    def add_execution(self, job_id: UUID, playbook: str, limit: str, tags: list[str] | None) -> UUID:
        return self.c.execute("""INSERT INTO ansible_executions(job_id, playbook, limit_hosts, tags,
                                                                 status, started_at)
                                 VALUES (%s,%s,%s,%s,'RUNNING',now()) RETURNING id""",
                              (job_id, playbook, limit, tags)).fetchone()["id"]

    def finish_execution(self, exec_id: UUID, status: str, rc: int, stats: dict) -> None:
        self.c.execute("""UPDATE ansible_executions SET status=%s, rc=%s, stats=%s, finished_at=now()
                          WHERE id=%s""", (status, rc, json.dumps(stats), exec_id))

    def add_results(self, job_id: UUID, exec_id: UUID, steps: list[dict]) -> None:
        for i, st in enumerate(steps, 1):
            self.c.execute("""INSERT INTO job_results(job_id, execution_id, step, step_order, status,
                                                      changed, output)
                              VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                           (job_id, exec_id, st["step"], i, st["status"], st["changed"],
                            json.dumps({"tasks": st["tasks"]})))

    def results(self, job_id: UUID) -> list[dict]:
        return self.c.execute("""SELECT step, step_order, status, changed, output
                                 FROM job_results WHERE job_id=%s ORDER BY step_order""",
                              (job_id,)).fetchall()

    def executions(self, job_id: UUID) -> list[dict]:
        return self.c.execute("""SELECT id, playbook, limit_hosts, status, rc, stats, started_at,
                                        finished_at FROM ansible_executions WHERE job_id=%s""",
                              (job_id,)).fetchall()

    def counts_recent(self) -> dict[str, int]:
        rows = self.c.execute("""SELECT status, count(*) AS n FROM jobs
                                 WHERE created_at > now() - interval '7 days' GROUP BY status""")
        return {r["status"]: r["n"] for r in rows}


# ----------------------------------------------------------------------------- inventario
class DeviceRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def activate_spoke(self, site_id: UUID, hostname: str, mgmt: str) -> UUID:
        self.c.execute("UPDATE devices SET is_active=FALSE, decommissioned_at=now() "
                       "WHERE hostname=%s AND is_active AND site_id IS DISTINCT FROM %s",
                       (hostname, site_id))
        row = self.c.execute("SELECT id FROM devices WHERE site_id=%s AND is_active",
                             (site_id,)).fetchone()
        if row:
            return row["id"]
        tpl = self.c.execute("SELECT id FROM device_templates WHERE name='spoke-iol-small'").fetchone()
        return self.c.execute("""INSERT INTO devices(site_id, template_id, hostname, role, mgmt_address,
                                                     os_version)
                                 VALUES (%s,%s,%s,'SPOKE',%s,'IOL 15.7(3)M2') RETURNING id""",
                              (site_id, tpl["id"] if tpl else None, hostname, mgmt)).fetchone()["id"]

    def deactivate_site(self, site_id: UUID) -> None:
        self.c.execute("UPDATE devices SET is_active=FALSE, decommissioned_at=now() "
                       "WHERE site_id=%s AND is_active", (site_id,))

    def list(self) -> list[dict]:
        return self.c.execute("""
            SELECT d.id, d.hostname, d.role, host(d.mgmt_address) AS mgmt_address, d.os_version,
                   d.is_active, d.created_at, d.decommissioned_at,
                   s.id AS site_id, s.code AS site_code, s.name AS site_name, s.status AS site_status,
                   z.state AS zabbix_state, z.zabbix_hostid
            FROM devices d LEFT JOIN sites s ON s.id=d.site_id
            LEFT JOIN LATERAL (SELECT state, zabbix_hostid FROM zabbix_hosts
                               WHERE device_id=d.id ORDER BY created_at DESC LIMIT 1) z ON TRUE
            ORDER BY d.is_active DESC, d.role, length(d.hostname), d.hostname""").fetchall()

    def active_hostnames(self) -> list[str]:
        return [r["hostname"] for r in
                self.c.execute("SELECT hostname FROM devices WHERE is_active ORDER BY hostname")]


class ZabbixHostRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def register(self, site_id: UUID, hostname: str, mgmt: str, site_code: str,
                 zabbix_hostid: str | None, state: str, error: str | None = None) -> None:
        dev = self.c.execute("SELECT id FROM devices WHERE site_id=%s AND is_active",
                             (site_id,)).fetchone()
        if not dev:
            return
        self.c.execute("UPDATE zabbix_hosts SET state='REMOVED', removed_at=now() "
                       "WHERE device_id=%s AND state<>'REMOVED'", (dev["id"],))
        self.c.execute("""
            INSERT INTO zabbix_hosts(device_id, zabbix_hostid, technical_name, host_groups, templates,
                                     tags, snmp_address, state, last_sync_at, last_error)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)""",
            (dev["id"], zabbix_hostid, hostname, ["Sucursales"], ["Cisco IOS by SNMP"],
             json.dumps({"sitio": site_code, "rol": "spoke", "gestionado_por": "portal-xyz"}),
             mgmt, state, error))

    def remove_for_site(self, site_id: UUID) -> None:
        self.c.execute("""UPDATE zabbix_hosts z SET state='REMOVED', removed_at=now(), last_sync_at=now()
                          FROM devices d WHERE d.id=z.device_id AND d.site_id=%s
                          AND z.state<>'REMOVED'""", (site_id,))

    def live(self) -> list[dict]:
        return self.c.execute("""SELECT z.*, d.hostname FROM zabbix_hosts z
                                 JOIN devices d ON d.id=z.device_id
                                 WHERE z.state<>'REMOVED'""").fetchall()

    def set_state(self, zid: UUID, state: str, hostid: str | None, error: str | None) -> None:
        self.c.execute("""UPDATE zabbix_hosts SET state=%s, zabbix_hostid=COALESCE(%s, zabbix_hostid),
                                 last_error=%s, last_sync_at=now() WHERE id=%s""",
                       (state, hostid, error, zid))

    def for_site(self, site_id: UUID) -> list[dict]:
        return self.c.execute("""SELECT z.* FROM zabbix_hosts z JOIN devices d ON d.id=z.device_id
                                 WHERE d.site_id=%s ORDER BY z.created_at DESC""",
                              (site_id,)).fetchall()


# ----------------------------------------------------------------------------- eventos/auditoría
class HealthRepo:
    """Resultado del ping a cada router (lo escribe el worker)."""
    MONITORED = ("ACTIVE", "DECOMMISSION_FAILED")

    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def targets(self) -> list[dict]:
        """Sitios vivos sin un trabajo en curso (durante un alta o baja el router se reconfigura)."""
        return self.c.execute("""
            SELECT s.id, s.code, s.name, s.site_number, h.state, h.failures
            FROM sites s
            LEFT JOIN site_health h ON h.site_id = s.id
            WHERE s.status = ANY(%s)
              AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.site_id = s.id
                              AND j.status IN ('QUEUED','RUNNING'))""",
            (list(self.MONITORED),)).fetchall()

    def record(self, site_id: UUID, ok: bool, needed_failures: int) -> str | None:
        """Guarda una prueba. Devuelve el nuevo estado si cambió (para auditarlo)."""
        r = self.c.execute("SELECT * FROM site_health WHERE site_id = %s FOR UPDATE",
                           (site_id,)).fetchone()
        if r is None:
            state = "REACHABLE" if ok else ("UNREACHABLE" if needed_failures <= 1 else None)
            self.c.execute(
                """INSERT INTO site_health(site_id, state, since, checked_at, failures, first_failure_at)
                   VALUES (%s, %s, now(), now(), %s, %s)""",
                (site_id, state or "REACHABLE", 0 if ok else 1, None if ok else _now()))
            return None if ok else state
        if ok:
            self.c.execute(
                """UPDATE site_health SET checked_at = now(), failures = 0, first_failure_at = NULL,
                          state = 'REACHABLE', prompt_snoozed_until = NULL,
                          since = CASE WHEN state = 'REACHABLE' THEN since ELSE now() END
                   WHERE site_id = %s""", (site_id,))
            return "REACHABLE" if r["state"] != "REACHABLE" else None
        failures = r["failures"] + 1
        first = r["first_failure_at"] or _now()
        down = failures >= needed_failures
        self.c.execute(
            """UPDATE site_health SET checked_at = now(), failures = %s, first_failure_at = %s,
                      state = CASE WHEN %s THEN 'UNREACHABLE' ELSE state END,
                      since = CASE WHEN %s AND state <> 'UNREACHABLE' THEN %s ELSE since END
               WHERE site_id = %s""",
            (min(failures, 32000), first, down, down, first, site_id))
        return "UNREACHABLE" if down and r["state"] != "UNREACHABLE" else None

    def get(self, site_id: UUID) -> dict | None:
        return self.c.execute("SELECT * FROM site_health WHERE site_id = %s", (site_id,)).fetchone()

    def offline_alerts(self, minutes: int) -> list[dict]:
        """Sucursales sin respuesta desde hace más de `minutes`, que se pueden retirar."""
        return self.c.execute("""
            SELECT s.id, s.code, s.name, s.site_number, h.since, h.checked_at,
                   floor(extract(epoch FROM now() - h.since) / 60)::int AS minutes_down
            FROM site_health h
            JOIN sites s ON s.id = h.site_id
            WHERE h.state = 'UNREACHABLE'
              AND h.since <= now() - make_interval(mins => %s)
              AND (h.prompt_snoozed_until IS NULL OR h.prompt_snoozed_until <= now())
              AND s.status IN ('ACTIVE','DECOMMISSION_FAILED') AND NOT s.protected
              AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.site_id = s.id
                              AND j.status IN ('QUEUED','RUNNING'))
            ORDER BY h.since""", (minutes,)).fetchall()

    def snooze(self, site_id: UUID, minutes: int) -> bool:
        cur = self.c.execute(
            """UPDATE site_health SET prompt_snoozed_until = now() + make_interval(mins => %s)
               WHERE site_id = %s AND state = 'UNREACHABLE'""", (minutes, site_id))
        return cur.rowcount == 1

    def clear(self, site_id: UUID) -> None:
        self.c.execute("DELETE FROM site_health WHERE site_id = %s", (site_id,))


def _now() -> datetime:
    return datetime.now(UTC)


class EventRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    def record(self, aggregate: str, aggregate_id: str, event_type: str, payload: dict) -> None:
        self.c.execute("""INSERT INTO events(aggregate_type, aggregate_id, event_type, payload)
                          VALUES (%s,%s,%s,%s)""",
                       (aggregate, aggregate_id, event_type, json.dumps(payload, default=str)))

    def for_aggregate(self, aggregate_id: str) -> list[dict]:
        return self.c.execute("""SELECT event_type, payload, occurred_at FROM events
                                 WHERE aggregate_id=%s ORDER BY id""", (aggregate_id,)).fetchall()


def _audit_hash(prev: bytes | None, content: dict) -> bytes:
    body = json.dumps(content, sort_keys=True, default=str, ensure_ascii=False).encode()
    return hashlib.sha256((prev or b"") + body).digest()


def _audit_content(r: dict) -> dict:
    occurred = r["occurred_at"]
    if isinstance(occurred, datetime):
        occurred = occurred.astimezone(UTC).isoformat()
    return {"occurred_at": occurred, "actor": str(r["actor_user_id"]) if r["actor_user_id"] else None,
            "actor_type": r["actor_type"], "action": r["action"], "target_type": r["target_type"],
            "target_id": r["target_id"], "source_ip": str(r["source_ip"]) if r["source_ip"] else None,
            "before": r["before_state"], "after": r["after_state"], "outcome": r["outcome"]}


class AuditRepo:
    """Bitácora encadenada: row_hash = sha256(prev_hash || contenido). Solo inserción."""

    def __init__(self, conn: Connection, source_ip: str | None = None,
                 user_agent: str | None = None, request_id: str | None = None) -> None:
        self.c = conn
        self.source_ip = source_ip
        self.user_agent = user_agent
        self.request_id = request_id

    def write(self, actor: UUID | None, action: str, target_type: str, target_id: str,
              outcome: str, before: dict | None = None, after: dict | None = None,
              actor_type: str = "USER") -> None:
        self.c.execute("SELECT pg_advisory_xact_lock(4242)")   # encadenamiento serializado
        prev = self.c.execute("SELECT row_hash FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = bytes(prev["row_hash"]) if prev else None
        row = {"occurred_at": datetime.now(UTC), "actor_user_id": actor, "actor_type": actor_type,
               "action": action, "target_type": target_type, "target_id": str(target_id),
               "source_ip": self.source_ip, "before_state": before, "after_state": after,
               "outcome": outcome}
        row_hash = _audit_hash(prev_hash, _audit_content(row))
        self.c.execute("""
            INSERT INTO audit_logs(occurred_at, actor_user_id, actor_type, action, target_type,
                                   target_id, request_id, source_ip, user_agent, before_state,
                                   after_state, outcome, prev_hash, row_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (row["occurred_at"], actor, actor_type, action, target_type, str(target_id),
             self.request_id, self.source_ip, (self.user_agent or "")[:300],
             json.dumps(before, default=str) if before is not None else None,
             json.dumps(after, default=str) if after is not None else None,
             outcome, prev_hash, row_hash))

    def list(self, action: str | None, target_id: str | None, limit: int, offset: int) -> list[dict]:
        conds, args = [], []
        if action:
            conds.append("a.action LIKE %s")
            args.append(action + "%")
        if target_id:
            conds.append("a.target_id = %s")
            args.append(target_id)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return self.c.execute(f"""
            SELECT a.id, a.occurred_at, a.actor_type, u.username AS actor, a.action, a.target_type,
                   a.target_id, host(a.source_ip) AS source_ip, a.before_state, a.after_state,
                   a.outcome, encode(a.row_hash, 'hex') AS row_hash
            FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id
            {where} ORDER BY a.id DESC LIMIT %s OFFSET %s""", [*args, limit, offset]).fetchall()

    def verify_chain(self) -> dict:
        prev: bytes | None = None
        n = 0
        for r in self.c.execute("SELECT * FROM audit_logs ORDER BY id"):
            stored_prev = bytes(r["prev_hash"]) if r["prev_hash"] is not None else None
            if stored_prev != prev or _audit_hash(prev, _audit_content(r)) != bytes(r["row_hash"]):
                return {"valid": False, "checked": n, "broken_at_id": r["id"]}
            prev = bytes(r["row_hash"])
            n += 1
        return {"valid": True, "checked": n, "broken_at_id": None}


# ----------------------------------------------------------------------------- usuarios
class UserRepo:
    def __init__(self, conn: Connection) -> None:
        self.c = conn

    _COLS = """u.id, u.username, u.email, u.full_name, u.is_active, u.mfa_enabled,
               u.last_login_at, u.created_at, u.locked_until,
               COALESCE(array_agg(r.name ORDER BY r.name) FILTER (WHERE r.name IS NOT NULL), '{}')
                 AS roles"""

    def by_username(self, username: str) -> dict | None:
        return self.c.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()

    def by_id(self, user_id: UUID) -> dict | None:
        return self.c.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()

    def public(self, user_id: UUID) -> dict | None:
        return self.c.execute(f"""SELECT {self._COLS} FROM users u
                                  LEFT JOIN user_roles ur ON ur.user_id=u.id
                                  LEFT JOIN roles r ON r.id=ur.role_id
                                  WHERE u.id=%s GROUP BY u.id""", (user_id,)).fetchone()

    def list(self) -> list[dict]:
        return self.c.execute(f"""SELECT {self._COLS} FROM users u
                                  LEFT JOIN user_roles ur ON ur.user_id=u.id
                                  LEFT JOIN roles r ON r.id=ur.role_id
                                  WHERE u.username <> 'system'
                                  GROUP BY u.id ORDER BY u.username""").fetchall()

    def permissions(self, user_id: UUID) -> set[str]:
        rows = self.c.execute("""SELECT DISTINCT p.code FROM user_roles ur
                                 JOIN role_permissions rp ON rp.role_id=ur.role_id
                                 JOIN permissions p ON p.id=rp.permission_id
                                 WHERE ur.user_id=%s""", (user_id,))
        return {r["code"] for r in rows}

    def roles(self) -> list[dict]:
        return self.c.execute("SELECT name, description FROM roles ORDER BY id").fetchall()

    def create(self, username: str, email: str, full_name: str, password_hash: str) -> UUID:
        try:
            with self.c.transaction():   # savepoint
                return self.c.execute("""INSERT INTO users(username, email, full_name, password_hash,
                                                           password_changed_at)
                                         VALUES (%s,%s,%s,%s,now()) RETURNING id""",
                                      (username, email, full_name, password_hash)).fetchone()["id"]
        except errors.UniqueViolation as exc:
            raise DomainError("El usuario o el correo ya existen") from exc

    def set_roles(self, user_id: UUID, roles: list[str]) -> None:
        known = {r["name"] for r in self.roles()}
        bad = set(roles) - known
        if bad:
            raise DomainError(f"Roles desconocidos: {', '.join(sorted(bad))}")
        self.c.execute("DELETE FROM user_roles WHERE user_id=%s", (user_id,))
        for name in roles:
            self.c.execute("""INSERT INTO user_roles(user_id, role_id)
                              SELECT %s, id FROM roles WHERE name=%s""", (user_id, name))

    def update(self, user_id: UUID, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=%s" for k in fields)
        self.c.execute(f"UPDATE users SET {sets} WHERE id=%s", [*fields.values(), user_id])
