"""Configuración por variables de entorno (archivo /opt/xyz/portal/portal.env en la EC2)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql://portal:portal@127.0.0.1:5432/portal"))
    secret_key: str = field(default_factory=lambda: _env("APP_SECRET_KEY", "dev-solo-pruebas"))
    cookie_secure: bool = field(default_factory=lambda: _env("COOKIE_SECURE", "true") == "true")
    cookie_path: str = field(default_factory=lambda: _env("COOKIE_PATH", "/portal_heladeria"))
    session_hours: int = field(default_factory=lambda: int(_env("SESSION_HOURS", "8")))
    mfa_issuer: str = field(default_factory=lambda: _env("MFA_ISSUER", "Heladeria Leche de Cabra"))
    # Ansible en la misma EC2
    xyz_base: str = field(default_factory=lambda: _env("XYZ_BASE", "/opt/xyz"))
    job_timeout: int = field(default_factory=lambda: int(_env("JOB_TIMEOUT", "1800")))
    # Zabbix (solo lectura desde el portal; el alta/baja la hace Ansible)
    zabbix_url: str = field(default_factory=lambda: _env("ZABBIX_URL", ""))
    zabbix_token: str = field(default_factory=lambda: _env("ZABBIX_API_TOKEN", ""))
    # Infraestructura que ningún sitio puede pisar (separadas por coma)
    reserved_underlay_hosts: str = field(default_factory=lambda: _env(
        "RESERVED_UNDERLAY_HOSTS", "172.16.0.20"))            # Ubuntu: Zabbix, NTP, salto
    reserved_networks: str = field(default_factory=lambda: _env(
        "RESERVED_NETWORKS", "10.99.0.0/24,10.254.0.0/24"))   # WireGuard y loopbacks
    # Conectividad: ping a cada router desde el worker
    health_interval: int = field(default_factory=lambda: int(_env("HEALTH_INTERVAL", "60")))
    health_failures: int = field(default_factory=lambda: int(_env("HEALTH_FAILURES", "2")))
    offline_prompt_minutes: int = field(default_factory=lambda: int(_env(
        "OFFLINE_PROMPT_MINUTES", "30")))     # tiempo sin respuesta antes de preguntar al admin
    hub_hosts: str = field(default_factory=lambda: _env("HUB_HOSTS", "R1=172.16.0.1,R2=172.16.0.2"))
    # Regla de direccionamiento del equipo
    birth_month: int = field(default_factory=lambda: int(_env("TEAM_BIRTH_MONTH", "12")))
    birth_day: int = field(default_factory=lambda: int(_env("TEAM_BIRTH_DAY", "28")))

    @property
    def run_job(self) -> str:
        return _env("RUN_JOB", f"{self.xyz_base}/ansible/bin/run-job.sh")

    @property
    def inventories_dir(self) -> str:
        return f"{self.xyz_base}/ansible/inventories"

    @property
    def jobs_dir(self) -> str:
        return f"{self.xyz_base}/jobs"


settings = Settings()
