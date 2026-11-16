"""Inventario dinámico de Ansible que lee el IPAM del portal.

Grupos que produce: hubs, spokes, zabbix. Las variables de host vienen del IPAM;
los secretos NO viajan por aquí: se leen en el runner desde AWS Secrets Manager.
"""
from __future__ import annotations

import json
import os
import urllib.request

from ansible.errors import AnsibleError
from ansible.plugins.inventory import BaseInventoryPlugin

DOCUMENTATION = r"""
name: portal_inventory
plugin_type: inventory
short_description: Inventario desde la API del portal de Heladería Leche de Cabra
options:
  plugin:
    required: true
    choices: ['portal_inventory']
  api_url:
    type: str
    env: [{name: PORTAL_API_URL}]
  site_filter:
    type: str
    default: ''
    env: [{name: PORTAL_SITE_CODE}]
"""


class InventoryModule(BaseInventoryPlugin):
    NAME = "portal_inventory"

    def verify_file(self, path: str) -> bool:
        return super().verify_file(path) and path.endswith(("portal.yml", "portal.yaml"))

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache)
        self._read_config_data(path)
        api_url = (self.get_option("api_url") or "").rstrip("/")
        site = self.get_option("site_filter") or ""
        if not api_url:
            raise AnsibleError("PORTAL_API_URL no está definido")
        token = os.environ.get("PORTAL_RUNNER_TOKEN")
        if not token:
            raise AnsibleError("PORTAL_RUNNER_TOKEN no está definido")

        url = f"{api_url}/inventory/ansible" + (f"?site={site}" if site else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.load(resp)
        except Exception as exc:  # noqa: BLE001
            raise AnsibleError(f"No se pudo leer el inventario del portal: {exc}") from exc

        hostvars = data.get("_meta", {}).get("hostvars", {})
        for group, body in data.items():
            if group == "_meta":
                continue
            self.inventory.add_group(group)
            for host in body.get("hosts", []):
                self.inventory.add_host(host, group=group)
                for key, value in hostvars.get(host, {}).items():
                    self.inventory.set_variable(host, key, value)
