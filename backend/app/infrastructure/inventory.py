"""Genera inventories/site_R<s>.yml (el archivo que run-job.sh exige) desde el IPAM."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.config import settings

_KEYS = {  # recurso del IPAM -> variable de Ansible
    "UNDERLAY_V4": ("ansible_host", "ip"),
    "LOOPBACK_V4": ("loopback0", "ip"),
    "LAN_V4": ("lan_v4", "prefix"),
    "LAN_V6": ("lan_v6", "prefix"),
    "TUNNEL1_V4": ("tunnel1_v4", "ip"),
    "TUNNEL2_V4": ("tunnel2_v4", "ip"),
    "TUNNEL1_V6": ("tunnel1_v6", "ip"),
    "TUNNEL2_V6": ("tunnel2_v6", "ip"),
}


def render(site: dict, allocations: list[dict]) -> str:
    host = f"R{site['site_number']}"
    hv: dict = {"site_id": site["site_number"], "site_code": site["code"], "site_name": site["name"],
                "lan_interfaces": ["Ethernet0/1"]}
    for a in allocations:
        if a["resource"] in _KEYS and a["status"] in ("RESERVED", "ALLOCATED"):
            var, field = _KEYS[a["resource"]]
            hv[var] = a[field]
    missing = {v for v, _ in _KEYS.values()} - hv.keys()
    if missing:
        raise ValueError(f"Faltan asignaciones del IPAM: {', '.join(sorted(missing))}")
    # JSON es YAML válido: los valores (incluido el nombre comercial) quedan bien escapados
    lines = ["---", "# Generado por el portal desde el IPAM. No editar a mano.",
             "all:", "  children:", "    spokes:", "      hosts:", f"        {host}:"]
    order = ["ansible_host", "site_id", "site_code", "site_name", "loopback0", "lan_interfaces",
             "lan_v4", "lan_v6", "tunnel1_v4", "tunnel2_v4", "tunnel1_v6", "tunnel2_v6"]
    lines += [f"          {k}: {json.dumps(hv[k], ensure_ascii=False)}" for k in order]
    return "\n".join(lines) + "\n"


def path_for(site_number: int) -> Path:
    return Path(settings.inventories_dir) / f"site_R{site_number}.yml"


def write(site: dict, allocations: list[dict]) -> Path:
    target = path_for(site["site_number"])
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".site_", suffix=".yml")
    with os.fdopen(fd, "w") as f:
        f.write(render(site, allocations))
    os.chmod(tmp, 0o640)
    os.replace(tmp, target)       # escritura atómica
    return target


def archive(site_number: int, job_dir: Path) -> None:
    p = path_for(site_number)
    if p.exists():
        job_dir.mkdir(parents=True, exist_ok=True)
        os.replace(p, job_dir / p.name)
