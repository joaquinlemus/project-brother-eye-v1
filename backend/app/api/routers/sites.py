from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Principal, require, run_keep_audit, run_or_audit_failure
from app.application import sites as uc
from app.config import settings
from app.db import tx
from app.domain.errors import NotFound
from app.infrastructure import inventory
from app.infrastructure.repos import EventRepo, IpamRepo, JobRepo, SiteRepo, ZabbixHostRepo

router = APIRouter(prefix="/sites", tags=["sucursales"])


class SiteCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9-]{3,16}$", examples=["ZONA10"],
                      description="Código único de la sucursal; no se reutiliza")
    name: str = Field(min_length=3, max_length=80, pattern=r"^[\w\s.,()#&áéíóúÁÉÍÓÚñÑüÜ-]+$",
                      examples=["Heladería Zona 10"])
    site_number: int | None = Field(default=None, ge=3, le=124,
                                    description="R<s> del laboratorio; vacío = primer ID libre")


class DecommissionIn(BaseModel):
    confirm_code: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=3, max_length=200)


def _site(r: dict) -> dict:
    return {"id": r["id"], "code": r["code"], "name": r["name"], "status": r["status"],
            "site_number": r["site_number"], "hostname": f"R{r['site_number']}",
            "protected": r["protected"], "imported": r["imported"],
            "created_at": r["created_at"], "activated_at": r["activated_at"],
            "retired_at": r["retired_at"],
            "created_by": r.get("created_by_username"),
            "last_job": ({"id": r["last_job_id"], "type": r["last_job_type"],
                          "status": r["last_job_status"]} if r.get("last_job_id") else None),
            # Ping del worker; solo cuenta mientras el sitio está vivo (no en altas/bajas en curso)
            "reachability": ({"state": r["health_state"], "since": r["health_since"],
                              "checked_at": r["health_checked_at"]}
                             if r.get("health_state") and r["status"] != "RETIRED" else None)}


@router.get("", summary="Listar sucursales")
def list_sites(status_: str | None = Query(default=None, alias="status"),
               _: Principal = Depends(require("site:read"))) -> list[dict]:
    with tx() as conn:
        return [_site(r) for r in SiteRepo(conn).list(status_)]


@router.get("/available-ids", summary="Site IDs libres y en cuarentena")
def available_ids(_: Principal = Depends(require("site:read"))) -> dict:
    with tx() as conn:
        return uc.available_site_ids(conn)


@router.get("/offline-alerts", summary="Sucursales sin respuesta que esperan decisión del admin")
def offline_alerts(_: Principal = Depends(require("site:forget"))) -> dict:
    with tx() as conn:
        return {"threshold_minutes": settings.offline_prompt_minutes,
                "sites": uc.offline_alerts(conn)}


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Alta de sucursal")
def create_site(body: SiteCreate, request: Request, response: Response,
                p: Principal = Depends(require("site:create"))) -> dict:
    res = run_or_audit_failure(
        request, p.user_id, "site.create", body.code.upper(),
        lambda c, a: uc.create_site(c, a, code=body.code, name=body.name,
                                    site_number=body.site_number, actor=p.user_id))
    response.headers["Location"] = f"jobs/{res['job_id']}"
    a = res["addressing"]
    return {"site": {"id": res["site_id"], "hostname": res["hostname"], "status": "PROVISIONING"},
            "job": {"id": res["job_id"], "type": "PROVISION", "status": "QUEUED"},
            "allocations": {"site_id": a.site_id, "underlay": str(a.underlay.ip),
                            "loopback0": str(a.loopback0), "lan_v4": str(a.lan_v4[0]),
                            "lan_v6": str(a.lan_v6[0]), "tunnel0": [str(a.tunnel1_v4),
                                                                    str(a.tunnel1_v6)],
                            "tunnel1": [str(a.tunnel2_v4), str(a.tunnel2_v6)]}}


@router.get("/{site_id}", summary="Detalle: IPAM, trabajos, monitoreo e historial")
def get_site(site_id: UUID, _: Principal = Depends(require("site:read"))) -> dict:
    with tx() as conn:
        rows = [r for r in SiteRepo(conn).list() if r["id"] == site_id]
        if not rows:
            raise NotFound("La sucursal no existe")
        allocs = IpamRepo(conn).for_site(site_id)
        return {**_site(rows[0]), "notes": rows[0]["notes"],
                "allocations": allocs,
                "jobs": JobRepo(conn).list(site_id, None, 50, 0),
                "zabbix": ZabbixHostRepo(conn).for_site(site_id),
                "events": EventRepo(conn).for_aggregate(str(site_id))}


@router.get("/{site_id}/ansible-vars", summary="Inventario que recibe Ansible (vista previa)")
def ansible_vars(site_id: UUID, _: Principal = Depends(require("site:read"))) -> Response:
    with tx() as conn:
        row = SiteRepo(conn).get_row(site_id)
        if row is None:
            raise NotFound("La sucursal no existe")
        allocs = IpamRepo(conn).for_site(site_id)
    live = [a for a in allocs if a["status"] in ("RESERVED", "ALLOCATED")]
    text = inventory.render(row, live) if live else "# Sin recursos vivos en el IPAM (sitio retirado)\n"
    return Response(text, media_type="text/plain; charset=utf-8")


@router.post("/{site_id}/decommission", status_code=status.HTTP_202_ACCEPTED,
             summary="Baja de sucursal (requiere escribir el código)")
def decommission(site_id: UUID, body: DecommissionIn, request: Request,
                 p: Principal = Depends(require("site:decommission"))) -> dict:
    res = run_keep_audit(request, lambda c, a: uc.request_decommission(
        c, a, site_id=site_id, confirm_code=body.confirm_code, reason=body.reason, actor=p.user_id))
    return {"site": {"id": res["site_id"], "status": res["status"]},
            "job": {"id": res["job_id"], "type": "DECOMMISSION", "status": "QUEUED"}}


@router.post("/{site_id}/forget", status_code=status.HTTP_202_ACCEPTED,
             summary="Retirar una sucursal cuyo router ya no responde (no se conecta a él)")
def forget(site_id: UUID, body: DecommissionIn, request: Request,
           p: Principal = Depends(require("site:forget"))) -> dict:
    res = run_keep_audit(request, lambda c, a: uc.request_forget(
        c, a, site_id=site_id, confirm_code=body.confirm_code, reason=body.reason, actor=p.user_id))
    return {"site": {"id": res["site_id"], "status": res["status"]},
            "job": {"id": res["job_id"], "type": "FORGET", "status": "QUEUED"}}


@router.post("/{site_id}/offline-alert/keep", summary="La sucursal sigue en servicio: preguntar más tarde")
def keep_offline(site_id: UUID, request: Request,
                 p: Principal = Depends(require("site:forget"))) -> dict:
    with tx() as conn:
        return uc.snooze_offline(conn, _audit(request, conn), site_id=site_id, actor=p.user_id)


@router.post("/{site_id}/release-quarantine", summary="Liberar la cuarentena antes de tiempo")
def release_quarantine(site_id: UUID, request: Request,
                       p: Principal = Depends(require("ipam:release"))) -> dict:
    with tx() as conn:
        n = uc.release_quarantine(conn, _audit(request, conn), site_id=site_id, actor=p.user_id)
    return {"released": n}


def _audit(request, conn):
    from app.api.deps import audit_for
    return audit_for(request, conn)
