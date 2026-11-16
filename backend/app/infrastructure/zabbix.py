"""Cliente de solo lectura de la API de Zabbix 7.0 (el alta/baja la hace Ansible)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from app.config import settings

_cache: dict[str, tuple[float, object]] = {}
AVAILABLE = {"0": "UNKNOWN", "1": "AVAILABLE", "2": "UNAVAILABLE"}


class ZabbixError(Exception):
    pass


def configured() -> bool:
    return bool(settings.zabbix_url and settings.zabbix_token)


def _call(method: str, params: dict, timeout: int = 8):
    req = urllib.request.Request(  # noqa: S310 - URL fija de la configuración (http/https)
        settings.zabbix_url.rstrip("/") + "/api_jsonrpc.php",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json-rpc",
                 "Authorization": f"Bearer {settings.zabbix_token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ZabbixError(f"Zabbix no responde: {exc}") from exc
    if "error" in body:
        raise ZabbixError(body["error"].get("data") or body["error"].get("message"))
    return body["result"]


def hosts(use_cache: bool = True) -> list[dict]:
    """Hosts gestionados por el portal, con disponibilidad SNMP y problemas activos."""
    hit = _cache.get("hosts")
    if use_cache and hit and time.time() - hit[0] < 30:
        return hit[1]  # type: ignore[return-value]
    raw = _call("host.get", {
        "output": ["hostid", "host", "name", "status"],
        "selectInterfaces": ["ip", "type", "available", "error"],
        "selectTags": ["tag", "value"],
        "tags": [{"tag": "gestionado_por", "value": "portal-xyz", "operator": 1}],
    })
    ids = [h["hostid"] for h in raw]
    problems: dict[str, list] = {i: [] for i in ids}
    if ids:
        probs = _call("problem.get", {"hostids": ids, "output": ["eventid", "name", "severity",
                                                                  "objectid", "clock"],
                                      "recent": False, "sortfield": ["eventid"],
                                      "sortorder": "DESC"})
        if probs:
            trig = _call("trigger.get", {"triggerids": list({p["objectid"] for p in probs}),
                                         "output": ["triggerid"], "selectHosts": ["hostid"]})
            t2h = {t["triggerid"]: [h["hostid"] for h in t["hosts"]] for t in trig}
            for p in probs:
                for hid in t2h.get(p["objectid"], []):
                    problems.setdefault(hid, []).append(
                        {"name": p["name"], "severity": int(p["severity"]), "clock": int(p["clock"])})
    out = []
    for h in raw:
        snmp = next((i for i in h["interfaces"] if i["type"] == "2"), None)
        out.append({"hostid": h["hostid"], "host": h["host"], "name": h["name"],
                    "enabled": h["status"] == "0",
                    "ip": snmp["ip"] if snmp else None,
                    "snmp": AVAILABLE.get(snmp["available"], "UNKNOWN") if snmp else "NONE",
                    "snmp_error": (snmp or {}).get("error") or None,
                    "problems": problems.get(h["hostid"], [])})
    out.sort(key=lambda h: (len(h["host"]), h["host"]))
    _cache["hosts"] = (time.time(), out)
    return out


def find_host(hostname: str) -> dict | None:
    r = _call("host.get", {"filter": {"host": [hostname]}, "output": ["hostid", "status"]})
    return r[0] if r else None
