"""Prueba de conectividad desde la EC2, por WireGuard, a la IP de underlay del router.

Primero abre una conexión TCP al puerto SSH: cualquier respuesta del router (aceptar o rechazar)
indica que está vivo, y no necesita privilegios. Si no hay respuesta, intenta un ping ICMP.
La IP viene del IPAM (172.16.0.s), nunca de un usuario.
"""
from __future__ import annotations

import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor


def tcp_alive(ip: str, port: int = 22, timeout_s: float = 3.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            return True
    except ConnectionRefusedError:
        return True               # el router respondió con RST: está vivo
    except OSError:
        return False              # tiempo agotado o red inalcanzable


def ping(ip: str, count: int = 2, timeout_s: int = 2) -> bool:
    try:
        r = subprocess.run(["ping", "-n", "-q", "-c", str(count), "-W", str(timeout_s), ip],  # noqa: S603,S607
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=count * timeout_s + 5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def alive(ip: str) -> bool:
    return tcp_alive(ip) or ping(ip)


def ping_many(ips: list[str]) -> dict[str, bool]:
    if not ips:
        return {}
    with ThreadPoolExecutor(max_workers=min(16, len(ips))) as pool:
        return dict(zip(ips, pool.map(alive, ips), strict=True))
