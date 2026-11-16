from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.api.deps import Principal, audit_for, require
from app.application import health
from app.config import settings
from app.db import tx
from app.infrastructure import zabbix
from app.infrastructure.repos import DeviceRepo, JobRepo, SiteRepo, ZabbixHostRepo

log = logging.getLogger(__name__)
router = APIRouter(tags=["inventario y monitoreo"])


@router.get("/inventory/devices", summary="Routers: hubs y spokes")
def devices(_: Principal = Depends(require("site:read"))) -> list[dict]:
    with tx() as conn:
        return DeviceRepo(conn).list()


@router.get("/monitoring/hosts", summary="Estado en Zabbix (SNMP y problemas activos)")
def monitoring(_: Principal = Depends(require("site:read"))) -> dict:
    if not zabbix.configured():
        return {"configured": False, "hosts": [], "error": None}
    try:
        return {"configured": True, "hosts": zabbix.hosts(), "error": None}
    except zabbix.ZabbixError as exc:
        log.warning("Zabbix: %s", exc)        # el detalle (URL, error de red) solo en el log
        return {"configured": True, "hosts": [], "error": "Zabbix no responde en este momento."}


@router.post("/monitoring/reconcile", summary="Comparar el inventario con Zabbix")
def reconcile(request: Request, p: Principal = Depends(require("monitoring:reconcile"))) -> dict:
    """Sincronización: cada host vivo en la BD debe existir en Zabbix y viceversa."""
    if not zabbix.configured():
        return {"configured": False}
    remote = {h["host"]: h for h in zabbix.hosts(use_cache=False)}
    report = {"ok": [], "missing_in_zabbix": [], "unmanaged_in_zabbix": []}
    with tx() as conn:
        zrepo = ZabbixHostRepo(conn)
        local = zrepo.live()
        for z in local:
            h = remote.get(z["hostname"])
            if h:
                zrepo.set_state(z["id"], "REGISTERED", h["hostid"], None)
                report["ok"].append(z["hostname"])
            else:
                zrepo.set_state(z["id"], "DRIFT", None, "No existe en Zabbix")
                report["missing_in_zabbix"].append(z["hostname"])
        names = {z["hostname"] for z in local} | {"R1", "R2"}
        report["unmanaged_in_zabbix"] = sorted(set(remote) - names)
        audit_for(request, conn).write(p.user_id, "monitoring.reconcile", "Zabbix", "all",
                                       "SUCCESS", after=report)
    return {"configured": True, **report}


@router.get("/dashboard", summary="Resumen para la página principal")
def dashboard(_: Principal = Depends(require("site:read"))) -> dict:
    with tx() as conn:
        sites = SiteRepo(conn).counts()
        jobs = JobRepo(conn)
        recent = jobs.list(None, None, 8, 0)
        job_counts = jobs.counts_recent()
    hb = Path(settings.jobs_dir) / ".worker_heartbeat"
    try:
        age = int(time.time()) - int(hb.read_text().strip())
    except (OSError, ValueError):
        age = None
    return {"sites": sites, "jobs_7d": job_counts, "recent_jobs": recent,
            "worker": {"alive": age is not None and age < 30, "last_seen_s": age},
            "zabbix_configured": zabbix.configured(),
            "lab": health.read_status()}
