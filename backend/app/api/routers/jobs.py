from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import Principal, audit_for, require
from app.application import sites as uc
from app.config import settings
from app.db import tx
from app.domain.errors import NotFound
from app.infrastructure import ansible_log
from app.infrastructure.repos import JobRepo

router = APIRouter(prefix="/jobs", tags=["trabajos"])
MAX_CHUNK = 256 * 1024


@router.get("", summary="Listar trabajos")
def list_jobs(site_id: UUID | None = None, status_: str | None = Query(None, alias="status"),
              limit: int = Query(50, le=200), offset: int = 0,
              _: Principal = Depends(require("job:read"))) -> list[dict]:
    with tx() as conn:
        return JobRepo(conn).list(site_id, status_, limit, offset)


@router.get("/{job_id}", summary="Detalle del trabajo con pasos y resumen de Ansible")
def get_job(job_id: UUID, _: Principal = Depends(require("job:read"))) -> dict:
    with tx() as conn:
        jobs = JobRepo(conn)
        job = jobs.get(job_id)
        if job is None:
            raise NotFound("El trabajo no existe")
        job.pop("log_path", None)
        job.pop("extra_vars_s3", None)
        return {**job, "results": jobs.results(job_id), "executions": jobs.executions(job_id)}


@router.get("/{job_id}/log", summary="Salida de Ansible en vivo (por fragmentos)")
def get_log(job_id: UUID, offset: int = Query(0, ge=0),
            _: Principal = Depends(require("job:read"))) -> dict:
    with tx() as conn:
        job = JobRepo(conn).get(job_id)
    if job is None:
        raise NotFound("El trabajo no existe")
    done = job["status"] not in ("QUEUED", "RUNNING")
    path = job["log_path"]
    # Solo se leen archivos dentro de /opt/xyz/jobs (el path viene de la BD, igual se valida)
    if not path or not Path(path).resolve().is_relative_to(Path(settings.jobs_dir).resolve()):
        return {"offset": 0, "text": "", "done": done, "status": job["status"], "steps": []}
    p = Path(path)
    if not p.exists():
        return {"offset": 0, "text": "", "done": done, "status": job["status"], "steps": []}
    data = p.read_bytes()
    chunk = data[offset:offset + MAX_CHUNK]
    full = data.decode(errors="replace")
    return {"offset": offset + len(chunk), "text": chunk.decode(errors="replace"),
            "done": done and offset + len(chunk) >= len(data), "status": job["status"],
            "steps": ansible_log.parse(full)["steps"]}


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED, summary="Reintentar")
def retry(job_id: UUID, request: Request, p: Principal = Depends(require("job:retry"))) -> dict:
    with tx() as conn:
        res = uc.retry_job(conn, audit_for(request, conn), job_id=job_id, actor=p.user_id)
    return {"job": {"id": res["job_id"], "status": "QUEUED"}, "site_status": res["site_status"]}
