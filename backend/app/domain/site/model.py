"""Agregado Site: ciclo de vida de una sucursal. Sin dependencias de infraestructura."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import DomainError, InvalidTransition

SITE_CODE_RE = re.compile(r"^[A-Z0-9-]{3,16}$")


class SiteStatus(StrEnum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    PROVISION_FAILED = "PROVISION_FAILED"
    DECOMMISSIONING = "DECOMMISSIONING"
    DECOMMISSION_FAILED = "DECOMMISSION_FAILED"
    RETIRED = "RETIRED"


# Única fuente de verdad de las transiciones permitidas (sección 11.1 del documento)
TRANSITIONS: dict[SiteStatus, set[SiteStatus]] = {
    SiteStatus.PROVISIONING: {SiteStatus.ACTIVE, SiteStatus.PROVISION_FAILED},
    SiteStatus.PROVISION_FAILED: {SiteStatus.PROVISIONING, SiteStatus.DECOMMISSIONING},
    SiteStatus.ACTIVE: {SiteStatus.DECOMMISSIONING},
    SiteStatus.DECOMMISSIONING: {SiteStatus.RETIRED, SiteStatus.DECOMMISSION_FAILED},
    SiteStatus.DECOMMISSION_FAILED: {SiteStatus.DECOMMISSIONING},
    SiteStatus.RETIRED: set(),
}


@dataclass(frozen=True)
class SiteCode:
    value: str

    def __post_init__(self) -> None:
        # Este valor llega a hostnames y descripciones de IOS: validación estricta.
        if not SITE_CODE_RE.fullmatch(self.value):
            raise DomainError("El código de sitio debe cumplir ^[A-Z0-9-]{3,16}$")


@dataclass
class Site:
    code: SiteCode
    name: str
    site_number: int
    created_by: UUID
    id: UUID = field(default_factory=uuid4)
    status: SiteStatus = SiteStatus.PROVISIONING
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    version: int = 1
    events: list[dict] = field(default_factory=list)

    @property
    def hostname(self) -> str:
        return f"R{self.site_number}"   # convención del laboratorio: R1, R2, R3...

    def _move(self, target: SiteStatus) -> None:
        if target not in TRANSITIONS[self.status]:
            raise InvalidTransition(f"{self.status} -> {target} no está permitido")
        self.events.append({"type": "SiteStatusChanged", "from": self.status, "to": target})
        self.status = target
        self.version += 1

    # --- Comandos del agregado -------------------------------------------------
    def mark_active(self) -> None:
        self._move(SiteStatus.ACTIVE)
        self.activated_at = datetime.now(UTC)

    def mark_provision_failed(self) -> None:
        self._move(SiteStatus.PROVISION_FAILED)

    def retry_provision(self) -> None:
        self._move(SiteStatus.PROVISIONING)

    def request_decommission(self, confirm_code: str) -> None:
        if confirm_code != self.code.value:
            raise DomainError("El código de confirmación no coincide con el sitio")
        self._move(SiteStatus.DECOMMISSIONING)

    def mark_retired(self) -> None:
        self._move(SiteStatus.RETIRED)
        self.retired_at = datetime.now(UTC)

    def mark_decommission_failed(self) -> None:
        self._move(SiteStatus.DECOMMISSION_FAILED)

    def retry_decommission(self) -> None:
        self._move(SiteStatus.DECOMMISSIONING)
