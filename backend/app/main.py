"""API del portal (FastAPI). Detrás de Caddy en https://<IP>/portal_heladeria/api."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routers import audit, auth, inventory, ipam, jobs, sites, users
from app.domain.errors import (
    AuthError,
    ConcurrencyError,
    DomainError,
    Forbidden,
    IpamExhausted,
    NotFound,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Heladería Leche de Cabra - Portal SDN API",
    version="1.0.0",
    description="Alta y baja de sucursales DMVPN con Ansible, IPAM propio y monitoreo en Zabbix.",
    root_path=os.getenv("ROOT_PATH", ""),
    docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None,
)

API = "/api/v1"
for r in (auth.router, sites.router, jobs.router, ipam.router, audit.router, inventory.router,
          users.router):
    app.include_router(r, prefix=API)

_STATUS = [(NotFound, 404), (Forbidden, 403), (AuthError, 401), (IpamExhausted, 409),
           (ConcurrencyError, 409), (DomainError, 409)]


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
    code = next(c for t, c in _STATUS if isinstance(exc, t))
    return JSONResponse({"detail": str(exc)}, status_code=code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"] if x != "body")
        fields.append({"field": loc, "message": e["msg"]})
    return JSONResponse({"detail": "Datos inválidos", "fields": fields}, status_code=422)


@app.get(f"{API}/health", tags=["salud"])
def health() -> dict:
    from app.db import tx
    with tx() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}
