from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, require
from app.application.sites import PLAN
from app.db import tx
from app.infrastructure.repos import IpamRepo

router = APIRouter(prefix="/ipam", tags=["IPAM"])


@router.get("/pools", summary="Pools con uso por estado")
def pools(_: Principal = Depends(require("ipam:read"))) -> dict:
    with tx() as conn:
        rows = IpamRepo(conn).pools_usage()
    return {"rule": {"D": PLAN.bd.day, "MM": PLAN.bd.month, "MMDD": PLAN.bd.mmdd,
                     "max_site_id": PLAN.bd.max_site_id,
                     "lan_v4": "10.(D+s).0.0/24", "lan_v6": "2001:MMDD:s::/64",
                     "loopback": "10.254.0.s/32", "tunnel0": "192.168.5.s/25 · FD00:5::s/64",
                     "tunnel1": "192.168.5.(130+s)/25 · FD00:5:1::s/64"},
            "pools": rows}


@router.get("/allocations", summary="Asignaciones (filtrables por estado)")
def allocations(status: str | None = None, limit: int = Query(200, le=1000), offset: int = 0,
                _: Principal = Depends(require("ipam:read"))) -> list[dict]:
    with tx() as conn:
        return IpamRepo(conn).list(status, limit, offset)
