"""Conectividad de las sucursales.

El worker llama a check_all() cada HEALTH_INTERVAL segundos. Si los dos hubs tampoco responden,
el problema es el enlace con el laboratorio (WireGuard o el nodo Linux), no las sucursales: no
se marca ninguna como caída para no disparar preguntas de retiro falsas.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from app.config import settings
from app.db import tx
from app.infrastructure import probe
from app.infrastructure.repos import AuditRepo, EventRepo, HealthRepo

log = logging.getLogger("health")


def _hubs() -> dict[str, str]:
    out = {}
    for item in settings.hub_hosts.split(","):
        name, _, ip = item.strip().partition("=")
        if name and ip:
            out[name] = ip
    return out


def underlay_ip(site_number: int) -> str:
    return f"172.16.0.{site_number}"


def status_file() -> Path:
    return Path(settings.jobs_dir) / ".health.json"


def check_all(pinger: Callable[[list[str]], dict[str, bool]] = probe.ping_many) -> dict:
    with tx() as conn:
        targets = HealthRepo(conn).targets()
    hubs = _hubs()
    ips = list(hubs.values()) + [underlay_ip(t["site_number"]) for t in targets]
    result = pinger(ips)
    hubs_up = {name: result.get(ip, False) for name, ip in hubs.items()}
    lab_up = any(hubs_up.values()) if hubs else True
    summary = {"checked_at": int(time.time()), "lab_reachable": lab_up, "hubs": hubs_up,
               "sites": len(targets)}
    try:
        status_file().parent.mkdir(parents=True, exist_ok=True)
        status_file().write_text(json.dumps(summary))
    except OSError:
        pass
    if not lab_up:
        log.warning("Ningún hub responde: se omite la prueba de las sucursales (enlace al laboratorio)")
        return summary

    with tx() as conn:
        health, audit, events = HealthRepo(conn), AuditRepo(conn), EventRepo(conn)
        for t in targets:
            ok = result.get(underlay_ip(t["site_number"]), False)
            changed = health.record(t["id"], ok, settings.health_failures)
            if changed:
                down = changed == "UNREACHABLE"
                log.warning("R%s %s", t["site_number"], "sin respuesta" if down else "responde de nuevo")
                events.record("Site", str(t["id"]), "SiteUnreachable" if down else "SiteReachable",
                              {"ip": underlay_ip(t["site_number"])})
                audit.write(None, "site.unreachable" if down else "site.reachable", "Site",
                            str(t["id"]), "SUCCESS", actor_type="SYSTEM",
                            after={"hostname": f"R{t['site_number']}", "code": t["code"]})
    return summary


def read_status() -> dict | None:
    try:
        return json.loads(status_file().read_text())
    except (OSError, ValueError):
        return None


def loop(stop: Callable[[], bool]) -> None:
    log.info("Prueba de conectividad cada %s s", settings.health_interval)
    while not stop():
        try:
            check_all()
        except Exception:  # noqa: BLE001 - nunca debe tumbar al worker
            log.exception("Error en la prueba de conectividad")
        for _ in range(settings.health_interval):
            if stop():
                return
            time.sleep(1)
