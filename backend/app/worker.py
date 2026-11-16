"""Worker: toma trabajos de la cola (tabla jobs) y ejecuta Ansible con bin/run-job.sh.

Un trabajo a la vez: todos los jobs tocan los hubs, así que no se ejecutan en paralelo.
    python -m app.worker
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from app.application import health
from app.application import sites as uc
from app.config import settings
from app.db import tx
from app.infrastructure import ansible_log, inventory, zabbix
from app.infrastructure.repos import AuditRepo, IpamRepo, JobRepo, SiteRepo

log = logging.getLogger("worker")
ACTIONS = {"PROVISION": ("provision", "playbooks/site_provision.yml"),
           "DECOMMISSION": ("decommission", "playbooks/site_decommission.yml"),
           "FORGET": ("forget", "playbooks/site_forget.yml")}
_stop = False


def _heartbeat() -> None:
    p = Path(settings.jobs_dir) / ".worker_heartbeat"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(int(time.time())))


def _recover_orphans() -> None:
    """Un job RUNNING al arrancar quedó interrumpido (reinicio de la EC2 o del servicio)."""
    with tx() as conn:
        for job in JobRepo(conn).orphaned():
            log.warning("Job %s interrumpido: se marca como fallido", job["id"])
            uc.complete_job(conn, AuditRepo(conn), job=job, ok=False, zabbix=None,
                            error="Interrumpido: el worker se reinició durante la ejecución")


def _claim() -> tuple[dict, Path, object] | None:
    with tx() as conn:
        IpamRepo(conn).release_expired()
        jobs = JobRepo(conn)
        job = jobs.claim_next()
        if job is None:
            return None
        job_dir = Path(settings.jobs_dir) / str(job["id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        console = job_dir / "console.log"
        console.touch()
        jobs.mark_running(job["id"], str(console))
        site = SiteRepo(conn).get_row(job["site_id"])
        allocs = IpamRepo(conn).for_site(job["site_id"])
        _, playbook = ACTIONS[job["type"]]
        exec_id = jobs.add_execution(job["id"], playbook, f"R{site['site_number']},hubs", None)
    try:
        inventory.write(site, allocs)
    except (ValueError, OSError) as exc:
        console.write_text(f"ERROR preparando el inventario: {exc}\n")
        _finish(job, exec_id, console, rc=99, error=f"Inventario: {exc}")
        return None
    return job, console, exec_id


def _run(job: dict, console: Path) -> int:
    action, _ = ACTIONS[job["type"]]
    host = f"R{job['site_number']}"
    env = {**os.environ, "XYZ_BASE": settings.xyz_base, "PYTHONUNBUFFERED": "1",
           "ANSIBLE_FORCE_COLOR": "0", "ANSIBLE_NOCOLOR": "1"}
    cmd = ["bash", settings.run_job, str(job["id"]), action, host]
    log.info("Ejecutando %s", " ".join(cmd))
    with console.open("ab") as out:
        out.write(f"$ run-job.sh {job['id']} {action} {host}\n\n".encode())
        out.flush()
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,  # noqa: S603
                                cwd=f"{settings.xyz_base}/ansible", env=env,
                                start_new_session=True)
        try:
            return proc.wait(timeout=settings.job_timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            time.sleep(5)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            out.write(f"\nERROR: tiempo máximo excedido ({settings.job_timeout} s)\n".encode())
            return 124


def _error_summary(text: str, parsed: dict, rc: int) -> str:
    failed = next((s for s in parsed["steps"] if s["status"] == "FAILED"), None)
    detail = ""
    for line in text.splitlines():
        if line.startswith("fatal:") and "...ignoring" not in line:
            detail = line
    if not detail:
        tail = [ln for ln in text.splitlines() if ln.strip()][-3:]
        detail = " | ".join(tail)
    where = f"{failed['label']}: " if failed else ""
    return f"{where}{detail}"[:600] or f"run-job.sh terminó con código {rc}"


def _zabbix_state(job: dict) -> dict | None:
    if job["type"] != "PROVISION" or not zabbix.configured():
        return None
    try:
        h = zabbix.find_host(f"R{job['site_number']}")
    except zabbix.ZabbixError as exc:
        return {"state": "ERROR", "error": str(exc)}
    if h is None:
        return {"state": "ERROR", "error": "El host no aparece en Zabbix después del alta"}
    return {"state": "REGISTERED", "hostid": h["hostid"]}


def _finish(job: dict, exec_id, console: Path, rc: int, error: str | None = None) -> None:
    text = console.read_text(errors="replace") if console.exists() else ""
    parsed = ansible_log.parse(text)
    ok = rc == 0
    if not ok and error is None:
        error = _error_summary(text, parsed, rc)
    zbx = _zabbix_state(job) if ok else None
    with tx() as conn:
        jobs = JobRepo(conn)
        jobs.finish_execution(exec_id, "SUCCEEDED" if ok else "FAILED", rc, parsed["recap"])
        jobs.add_results(job["id"], exec_id, [
            {"step": s["label"], "status": s["status"] if s["status"] != "RUNNING" else "FAILED",
             "changed": s["changed"], "tasks": s["tasks"]} for s in parsed["steps"]])
        status = uc.complete_job(conn, AuditRepo(conn), job=job, ok=ok, error=error, zabbix=zbx)
    if ok and job["type"] in ("DECOMMISSION", "FORGET"):
        inventory.archive(job["site_number"], console.parent)
    log.info("Job %s %s -> sitio %s", job["id"], "OK" if ok else f"FALLÓ (rc={rc})", status)


def run_forever(poll: float = 3.0) -> None:
    _recover_orphans()
    if settings.health_interval > 0:
        threading.Thread(target=health.loop, args=(lambda: _stop,), name="health",
                         daemon=True).start()
    log.info("Worker listo (base %s)", settings.xyz_base)
    while not _stop:
        _heartbeat()
        try:
            claimed = _claim()
        except Exception:  # noqa: BLE001 - la BD puede estar reiniciándose
            log.exception("Error tomando un trabajo")
            time.sleep(10)
            continue
        if claimed is None:
            time.sleep(poll)
            continue
        job, console, exec_id = claimed
        rc = _run(job, console)
        try:
            _finish(job, exec_id, console, rc)
        except Exception:  # noqa: BLE001
            log.exception("Error registrando el resultado del job %s", job["id"])


def _graceful(*_):
    global _stop
    _stop = True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _graceful)
    run_forever()
