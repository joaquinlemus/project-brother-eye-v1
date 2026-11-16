"""Convierte la salida de ansible-playbook en pasos legibles para el portal."""
from __future__ import annotations

import re

STEP_LABELS = {
    "fvrf": "VRF de gestión (INET)",
    "base": "Configuración base, AAA, NTP, syslog",
    "crypto_ikev2": "IPsec IKEv2",
    "lan": "Loopback y LAN IPv4/IPv6",
    "dmvpn_spoke": "Túneles DMVPN (Hub 1 y Hub 2)",
    "routing": "OSPFv2 y OSPFv3",
    "snmpv3": "SNMPv3",
    "verify": "Verificación (IKEv2, NHRP, OSPF)",
    "zabbix_host": "Monitoreo en Zabbix",
    "decommission": "Retiro de configuración",
    "_hubs": "Verificación en los hubs",
    "_save": "Guardar configuración",
    "_probe": "Conectividad SSH",
}
_TASK = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_RESULT = re.compile(r"^(?P<st>ok|changed|fatal|failed|skipping|unreachable): \[(?P<host>[^\]]+)\]")
_RECAP = re.compile(r"^(?P<host>\S+)\s+:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
                    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)\s+"
                    r"skipped=(?P<skipped>\d+)\s+rescued=(?P<rescued>\d+)\s+ignored=(?P<ignored>\d+)")


def _step_for(task: str) -> str:
    if " : " in task:
        role = task.split(" : ", 1)[0].strip()
        return role if role in STEP_LABELS else role
    low = task.lower()
    if "ssh" in low:
        return "_probe"
    if "guardar" in low:
        return "_save"
    if "nhrp" in low or "spoke no debe" in low:
        return "_hubs"
    return "_other"


def parse(text: str) -> dict:
    steps: dict[str, dict] = {}
    order: list[str] = []
    current: str | None = None
    lines = text.splitlines()
    recap: dict[str, dict] = {}
    in_recap = False
    for i, line in enumerate(lines):
        m = _TASK.match(line)
        if m:
            name = m.group("name")
            current = _step_for(name)
            if current == "_other":
                current = None
                continue
            if current not in steps:
                steps[current] = {"step": current, "label": STEP_LABELS.get(current, current),
                                  "status": "RUNNING", "changed": False, "tasks": 0, "failed": 0}
                order.append(current)
            steps[current]["tasks"] += 1
            continue
        if line.startswith("PLAY RECAP"):
            in_recap = True
            current = None
            continue
        if in_recap:
            r = _RECAP.match(line)
            if r:
                recap[r.group("host")] = {k: int(v) for k, v in r.groupdict().items() if k != "host"}
            continue
        r = _RESULT.match(line)
        if r and current:
            st = r.group("st")
            ignored = any("...ignoring" in nxt for nxt in lines[i + 1:i + 4])
            if st == "changed":
                steps[current]["changed"] = True
            elif st in ("fatal", "failed", "unreachable") and not ignored:
                steps[current]["failed"] += 1
    # Un fallo se "rescata" si el mismo paso termina en otro posterior (p. ej. rescue): se respeta
    for idx, key in enumerate(order):
        s = steps[key]
        if s["failed"]:
            s["status"] = "FAILED"
        elif idx < len(order) - 1 or recap:
            s["status"] = "SUCCEEDED"
    return {"steps": [steps[k] for k in order], "recap": recap}
