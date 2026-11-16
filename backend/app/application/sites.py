"""Casos de uso de sucursales: alta, baja, reintento, cuarentena, importación y cierre de jobs.

Cada función recibe la conexión de UNA transacción: todo lo que escribe se confirma o se
revierte junto. La configuración del router ocurre después, en el worker.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from psycopg import Connection

from app.config import settings
from app.domain.errors import DomainError, Forbidden, IpamExhausted, NotFound
from app.domain.ipam.addressing import (
    FIRST_SPOKE_ID,
    AddressingPlan,
    TeamBirthday,
    first_free,
    reserved_site_ids,
)
from app.domain.site.model import Site, SiteCode, SiteStatus
from app.infrastructure.repos import (
    SYSTEM_USER,
    AuditRepo,
    DeviceRepo,
    EventRepo,
    HealthRepo,
    IpamRepo,
    JobRepo,
    SiteRepo,
    ZabbixHostRepo,
)

log = logging.getLogger(__name__)
PLAN = AddressingPlan(TeamBirthday(month=settings.birth_month, day=settings.birth_day))
ACTIVE_JOB = ("QUEUED", "RUNNING")


def _split(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def reserved_ids(rng: range) -> dict[int, str]:
    return reserved_site_ids(PLAN, rng, _split(settings.reserved_underlay_hosts),
                             _split(settings.reserved_networks))


def _unusable(ipam: IpamRepo, rng: range) -> tuple[dict[int, dict], dict[int, str]]:
    return ipam.used_site_ids(), reserved_ids(rng)


def _id_range(ipam: IpamRepo) -> range:
    pool = ipam.site_id_pool()
    lo = max(FIRST_SPOKE_ID, pool["int_min"])
    hi = min(pool["int_max"], PLAN.bd.max_site_id)
    return range(lo, hi + 1)


def available_site_ids(conn: Connection) -> dict:
    ipam = IpamRepo(conn)
    ipam.release_expired()
    rng = _id_range(ipam)
    used, reserved = _unusable(ipam, rng)
    blocked = set(used) | set(reserved)
    free = [s for s in rng if s not in blocked]
    quarantined = [{"site_number": s, "hostname": f"R{s}", "until": r["quarantine_until"],
                    "site_code": r["code"]}
                   for s, r in sorted(used.items()) if r["status"] == "QUARANTINED"]
    # Los IDs reservados simplemente no se ofrecen: no se expone por qué (IPs de servidores y VPN)
    return {"min": rng.start, "max": rng.stop - 1, "suggested": first_free(rng, blocked),
            "free": free[:50], "free_count": len(free), "quarantined": quarantined}


def create_site(conn: Connection, audit: AuditRepo, *, code: str, name: str,
                site_number: int | None, actor: UUID) -> dict:
    site_code = SiteCode(code.strip().upper())
    sites, ipam, jobs = SiteRepo(conn), IpamRepo(conn), JobRepo(conn)
    if sites.code_exists(site_code.value):
        raise DomainError(f"El código {site_code.value} ya fue usado (los códigos no se reutilizan)")

    ipam.lock()                      # serializa altas concurrentes
    ipam.release_expired()
    rng = _id_range(ipam)
    used, reserved = _unusable(ipam, rng)
    if site_number is None:
        s = first_free(rng, set(used) | set(reserved))
        if s is None:
            raise IpamExhausted("No quedan Site IDs libres fuera de cuarentena")
    else:
        s = site_number
        if s not in rng:
            raise DomainError(f"El Site ID debe estar entre {rng.start} y {rng.stop - 1}")
        if s in reserved:
            # El motivo (IP de un servidor o red de la VPN) solo va al log del servidor; la
            # respuesta y la auditoría, que ven usuarios del portal, no lo exponen.
            log.warning("Alta rechazada: R%s reservado (%s)", s, reserved[s])
            raise DomainError(f"R{s} está reservado y no se puede asignar a una sucursal")
        if s in used:
            r = used[s]
            extra = (f" hasta {r['quarantine_until']:%Y-%m-%d %H:%M} UTC"
                     if r["status"] == "QUARANTINED" else "")
            raise DomainError(f"R{s} no está disponible: {r['status']} ({r['code']}){extra}")

    addressing = PLAN.derive(s)
    site = Site(code=site_code, name=name.strip(), site_number=s, created_by=actor)
    sites.add(site)
    job_id = jobs.create(site.id, "PROVISION", actor)
    ipam.reserve(site.id, addressing, job_id)     # EXCLUDE/UNIQUE en la BD: última barrera
    EventRepo(conn).record("Site", str(site.id), "SiteProvisioningRequested",
                           {"job_id": str(job_id), "code": site_code.value, "site_number": s})
    audit.write(actor, "site.create", "Site", str(site.id), "SUCCESS",
                after={"code": site_code.value, "name": site.name, "hostname": site.hostname,
                       "site_number": s, "job_id": str(job_id)})
    return {"site_id": site.id, "job_id": job_id, "addressing": addressing,
            "hostname": site.hostname}


def request_decommission(conn: Connection, audit: AuditRepo, *, site_id: UUID,
                         confirm_code: str, reason: str, actor: UUID) -> dict:
    """Solo lecturas antes de las validaciones: si algo se rechaza, la auditoría DENIED se confirma."""
    sites, jobs = SiteRepo(conn), JobRepo(conn)
    row = sites.get_row(site_id, lock=True)
    if row is None:
        raise NotFound("La sucursal no existe")
    if row["protected"]:
        audit.write(actor, "site.decommission", "Site", str(site_id), "DENIED",
                    after={"reason": "sitio protegido"})
        raise Forbidden(f"{row['code']} (R{row['site_number']}) es un sitio protegido: se configuró "
                        "a mano antes del portal y no se puede dar de baja desde aquí.")
    if confirm_code.strip() != row["code"]:
        audit.write(actor, "site.decommission", "Site", str(site_id), "DENIED",
                    after={"reason": "código de confirmación incorrecto"})
        raise DomainError("El código de confirmación no coincide con el de la sucursal")
    last = jobs.latest_for_site(site_id)
    if last and last["status"] in ACTIVE_JOB:
        raise DomainError("La sucursal ya tiene un trabajo en curso")

    site = SiteRepo.to_domain(row)
    before = site.status.value
    site.request_decommission(row["code"])           # valida la transición en el dominio
    sites.save(site)
    job_id = jobs.create(site.id, "DECOMMISSION", actor)
    EventRepo(conn).record("Site", str(site.id), "SiteDecommissionRequested",
                           {"job_id": str(job_id), "reason": reason})
    audit.write(actor, "site.decommission", "Site", str(site.id), "SUCCESS",
                before={"status": before}, after={"status": site.status.value, "reason": reason,
                                                  "job_id": str(job_id)})
    return {"site_id": site.id, "status": site.status.value, "job_id": job_id}


def offline_alerts(conn: Connection) -> list[dict]:
    rows = HealthRepo(conn).offline_alerts(settings.offline_prompt_minutes)
    return [{"site_id": r["id"], "code": r["code"], "name": r["name"],
             "hostname": f"R{r['site_number']}", "since": r["since"],
             "checked_at": r["checked_at"], "minutes_down": r["minutes_down"]} for r in rows]


def snooze_offline(conn: Connection, audit: AuditRepo, *, site_id: UUID, actor: UUID) -> dict:
    """El administrador indica que la sucursal sigue en servicio: se vuelve a preguntar más tarde."""
    row = SiteRepo(conn).get_row(site_id)
    if row is None:
        raise NotFound("La sucursal no existe")
    if not HealthRepo(conn).snooze(site_id, settings.offline_prompt_minutes):
        raise DomainError("La sucursal ya responde")
    audit.write(actor, "site.offline.keep", "Site", str(site_id), "SUCCESS",
                after={"hostname": f"R{row['site_number']}", "code": row["code"],
                       "ask_again_in_min": settings.offline_prompt_minutes})
    return {"ask_again_in_min": settings.offline_prompt_minutes}


def request_forget(conn: Connection, audit: AuditRepo, *, site_id: UUID, confirm_code: str,
                   reason: str, actor: UUID) -> dict:
    """Retiro de una sucursal cuyo router ya no existe. Ansible no se conecta al router:
    quita el host de Zabbix y limpia los hubs; el IPAM pasa a cuarentena como en una baja."""
    sites, jobs = SiteRepo(conn), JobRepo(conn)
    row = sites.get_row(site_id, lock=True)
    if row is None:
        raise NotFound("La sucursal no existe")
    if row["protected"]:
        audit.write(actor, "site.forget", "Site", str(site_id), "DENIED",
                    after={"reason": "sitio protegido"})
        raise Forbidden(f"{row['code']} (R{row['site_number']}) es un sitio protegido: se configuró "
                        "a mano antes del portal y no se puede retirar desde aquí.")
    if confirm_code.strip() != row["code"]:
        audit.write(actor, "site.forget", "Site", str(site_id), "DENIED",
                    after={"reason": "código de confirmación incorrecto"})
        raise DomainError("El código de confirmación no coincide con el de la sucursal")
    h = HealthRepo(conn).get(site_id)
    if h is None or h["state"] != "UNREACHABLE":
        raise DomainError(f"R{row['site_number']} responde: usa la baja normal, que también limpia el router")
    last = jobs.latest_for_site(site_id)
    if last and last["status"] in ACTIVE_JOB:
        raise DomainError("La sucursal ya tiene un trabajo en curso")

    site = SiteRepo.to_domain(row)
    before = site.status.value
    if site.status == SiteStatus.DECOMMISSION_FAILED:
        site.retry_decommission()
    else:
        site.request_decommission(row["code"])
    sites.save(site)
    job_id = jobs.create(site.id, "FORGET", actor)
    EventRepo(conn).record("Site", str(site.id), "SiteForgetRequested",
                           {"job_id": str(job_id), "reason": reason,
                            "unreachable_since": h["since"].isoformat()})
    audit.write(actor, "site.forget", "Site", str(site.id), "SUCCESS",
                before={"status": before},
                after={"status": site.status.value, "reason": reason, "job_id": str(job_id),
                       "unreachable_since": h["since"].isoformat()})
    return {"site_id": site.id, "status": site.status.value, "job_id": job_id}


def retry_job(conn: Connection, audit: AuditRepo, *, job_id: UUID, actor: UUID) -> dict:
    jobs, sites = JobRepo(conn), SiteRepo(conn)
    job = jobs.get(job_id)
    if job is None:
        raise NotFound("El trabajo no existe")
    if job["status"] != "FAILED":
        raise DomainError("Solo se pueden reintentar trabajos fallidos")
    latest = jobs.latest_for_site(job["site_id"])
    if latest["id"] != job["id"]:
        raise DomainError("Ya hay un trabajo más reciente para esta sucursal")
    site = sites.get(job["site_id"], lock=True)
    if job["type"] == "PROVISION":
        site.retry_provision()
    elif job["type"] in ("DECOMMISSION", "FORGET"):
        site.retry_decommission()
    else:
        raise DomainError("Este tipo de trabajo no se reintenta")
    sites.save(site)
    new_id = jobs.create(site.id, job["type"], actor, parent_job_id=job["id"],
                         attempt=job["attempt"] + 1)
    audit.write(actor, "job.retry", "Job", str(job_id), "SUCCESS",
                after={"new_job_id": str(new_id), "attempt": job["attempt"] + 1})
    return {"job_id": new_id, "site_status": site.status.value}


def release_quarantine(conn: Connection, audit: AuditRepo, *, site_id: UUID, actor: UUID) -> int:
    row = SiteRepo(conn).get_row(site_id)
    if row is None:
        raise NotFound("La sucursal no existe")
    n = IpamRepo(conn).release_now(site_id)
    if n == 0:
        raise DomainError("Esta sucursal no tiene recursos en cuarentena")
    audit.write(actor, "ipam.release", "Site", str(site_id), "SUCCESS",
                after={"code": row["code"], "hostname": f"R{row['site_number']}", "released": n})
    return n


def import_site(conn: Connection, audit: AuditRepo, *, site_number: int, code: str, name: str,
                protected: bool, notes: str | None = None) -> UUID:
    """Registra un sitio que ya existía antes del portal (R3, R4, o uno dado de alta por CLI)."""
    sites, ipam = SiteRepo(conn), IpamRepo(conn)
    site_code = SiteCode(code.upper())
    if sites.code_exists(site_code.value):
        raise DomainError(f"El código {site_code.value} ya existe")
    ipam.lock()
    reserved = reserved_ids(range(site_number, site_number + 1))
    if site_number in reserved:
        raise DomainError(f"R{site_number} no se puede usar: {reserved[site_number]}")
    if site_number in ipam.used_site_ids():
        raise DomainError(f"R{site_number} ya está registrado")
    addressing = PLAN.derive(site_number)
    site = Site(code=site_code, name=name, site_number=site_number, created_by=SYSTEM_USER,
                status=SiteStatus.ACTIVE, activated_at=datetime.now(UTC))
    sites.add(site, protected=protected, imported=True, notes=notes)
    ipam.reserve(site.id, addressing, None)
    ipam.allocate(site.id)
    DeviceRepo(conn).activate_spoke(site.id, site.hostname, str(addressing.underlay.ip))
    ZabbixHostRepo(conn).register(site.id, site.hostname, str(addressing.underlay.ip),
                                  site_code.value, None, "PENDING")
    audit.write(None, "site.import", "Site", str(site.id), "SUCCESS", actor_type="SYSTEM",
                after={"code": site_code.value, "hostname": site.hostname, "protected": protected})
    return site.id


def complete_job(conn: Connection, audit: AuditRepo, *, job: dict, ok: bool,
                 error: str | None, zabbix: dict | None) -> str:
    """Aplica el resultado de Ansible al agregado, al IPAM, al inventario y a Zabbix."""
    sites, ipam, jobs = SiteRepo(conn), IpamRepo(conn), JobRepo(conn)
    site = sites.get(job["site_id"], lock=True)
    host = site.hostname
    mgmt = f"172.16.0.{site.site_number}"
    jobs.finish(job["id"], "SUCCEEDED" if ok else "FAILED", error)

    if job["type"] == "PROVISION":
        if ok:
            site.mark_active()
            ipam.allocate(site.id)
            DeviceRepo(conn).activate_spoke(site.id, host, mgmt)
            z = zabbix or {}
            ZabbixHostRepo(conn).register(site.id, host, mgmt, site.code.value, z.get("hostid"),
                                          z.get("state", "PENDING"), z.get("error"))
            event, action = "SiteActivated", "site.activate"
        else:
            site.mark_provision_failed()
            event, action = "SiteProvisionFailed", "site.provision"
    else:
        if ok:
            site.mark_retired()
            ipam.quarantine(site.id)
            DeviceRepo(conn).deactivate_site(site.id)
            ZabbixHostRepo(conn).remove_for_site(site.id)
            HealthRepo(conn).clear(site.id)
            event, action = "SiteRetired", "site.retire"
        else:
            site.mark_decommission_failed()
            event, action = "SiteDecommissionFailed", "site.decommission.run"
    sites.save(site)
    EventRepo(conn).record("Site", str(site.id), event, {"job_id": str(job["id"]), "error": error})
    audit.write(None, action, "Site", str(site.id), "SUCCESS" if ok else "FAILURE",
                actor_type="RUNNER",
                after={"status": site.status.value, "job_id": str(job["id"]), "error": error})
    return site.status.value
