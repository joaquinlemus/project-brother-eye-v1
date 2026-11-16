from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, require
from app.db import tx
from app.infrastructure.repos import AuditRepo

router = APIRouter(prefix="/audit", tags=["auditoría"])


@router.get("", summary="Bitácora de auditoría")
def list_audit(action: str | None = None, target_id: str | None = None,
               limit: int = Query(100, le=500), offset: int = 0,
               _: Principal = Depends(require("audit:read"))) -> list[dict]:
    with tx() as conn:
        return AuditRepo(conn).list(action, target_id, limit, offset)


@router.get("/verify", summary="Verificar la cadena de hashes (detecta alteraciones)")
def verify(_: Principal = Depends(require("audit:read"))) -> dict:
    with tx() as conn:
        return AuditRepo(conn).verify_chain()
