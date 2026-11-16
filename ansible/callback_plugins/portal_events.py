"""Callback que envía cada resultado de tarea a la API del portal.

POST {PORTAL_API_URL}/internal/jobs/{PORTAL_JOB_ID}/events
El portal lo usa para mostrar el progreso en vivo y llenar job_results.
Los resultados con no_log llegan censurados por Ansible antes de este punto.
"""
from __future__ import annotations

import json
import os
import urllib.request

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = r"""
name: portal_events
type: notification
short_description: Publica eventos de Ansible en el portal de Heladería Leche de Cabra
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "portal_events"
    CALLBACK_NEEDS_ENABLED = True

    def __init__(self):
        super().__init__()
        self.api = os.environ.get("PORTAL_API_URL", "").rstrip("/")
        self.job = os.environ.get("PORTAL_JOB_ID")
        self.token = os.environ.get("PORTAL_RUNNER_TOKEN")

    def _post(self, payload: dict) -> None:
        if not (self.api and self.job and self.token):
            return
        req = urllib.request.Request(
            f"{self.api}/internal/jobs/{self.job}/events",
            data=json.dumps(payload, default=str).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)  # noqa: S310
        except Exception as exc:  # noqa: BLE001 - el job no debe fallar por la telemetría
            self._display.warning(f"portal_events: {exc}")

    def _event(self, kind: str, result) -> None:
        self._post({
            "type": kind,
            "host": result._host.get_name(),
            "task": result._task.get_name(),
            "role": getattr(result._task._role, "_role_name", None),
            "changed": result._result.get("changed", False),
            "msg": result._result.get("msg"),
        })

    def v2_runner_on_ok(self, result):
        self._event("ok", result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._event("ignored" if ignore_errors else "failed", result)

    def v2_runner_on_unreachable(self, result):
        self._event("unreachable", result)

    def v2_playbook_on_stats(self, stats):
        summary = {h: stats.summarize(h) for h in sorted(stats.processed.keys())}
        self._post({"type": "stats", "stats": summary, "custom": stats.custom})
