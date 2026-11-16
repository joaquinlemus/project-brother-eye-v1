"""Sesión por cookie HttpOnly, permisos por rol (desde la BD) y protección CSRF."""
from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.application import security as sec
from app.config import settings
from app.db import tx
from app.infrastructure.repos import AuditRepo, UserRepo

COOKIE = "portal_session"
CSRF_HEADER = "x-portal-csrf"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    username: str
    full_name: str
    roles: tuple[str, ...]
    permissions: frozenset[str]

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def client_ip(request: Request) -> str | None:
    # Caddy (127.0.0.1) agrega X-Forwarded-For; solo se confía en él si viene del proxy local
    peer = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd and peer in ("127.0.0.1", "::1") else peer
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def audit_for(request: Request, conn) -> AuditRepo:
    return AuditRepo(conn, source_ip=client_ip(request),
                     user_agent=request.headers.get("user-agent"),
                     request_id=request.headers.get("x-request-id") or str(uuid.uuid4()))


def current_user(request: Request) -> Principal:
    token = request.cookies.get(COOKIE)
    user_id = sec.read_token(token, "session") if token else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no iniciada o expirada")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Falta la cabecera anti-CSRF")
    with tx() as conn:
        users = UserRepo(conn)
        u = users.public(user_id)
        if not u or not u["is_active"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario desactivado")
        perms = users.permissions(user_id)
    return Principal(user_id=u["id"], username=u["username"], full_name=u["full_name"],
                     roles=tuple(u["roles"]), permissions=frozenset(perms))


def require(perm: str):
    def _dep(p: Principal = Depends(current_user)) -> Principal:
        if not p.can(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Tu rol no tiene el permiso {perm}")
        return p
    return _dep


def set_session(response, user_id: UUID) -> None:
    response.set_cookie(COOKIE, sec.make_token(user_id, "session", settings.session_hours * 60),
                        max_age=settings.session_hours * 3600, httponly=True,
                        secure=settings.cookie_secure, samesite="strict", path=settings.cookie_path)


def clear_session(response) -> None:
    response.delete_cookie(COOKIE, path=settings.cookie_path, secure=settings.cookie_secure,
                           httponly=True, samesite="strict")


def run_keep_audit(request: Request, fn):
    """Ejecuta fn(conn, audit). Si lanza DomainError, la transacción se CONFIRMA (para conservar
    la auditoría DENIED/FAILURE y los contadores de intentos) y luego se propaga el error.
    Solo para casos de uso que no escriben nada antes de validar."""
    from app.domain.errors import DomainError
    err: DomainError | None = None
    with tx() as conn:
        try:
            result = fn(conn, audit_for(request, conn))
        except DomainError as exc:
            err = exc
    if err is not None:
        raise err
    return result


def run_or_audit_failure(request: Request, actor: UUID, action: str, target: str, fn):
    """Ejecuta fn(conn, audit) con rollback total si falla, y registra el fallo aparte."""
    from app.domain.errors import DomainError
    try:
        with tx() as conn:
            return fn(conn, audit_for(request, conn))
    except DomainError as exc:
        with tx() as conn:
            audit_for(request, conn).write(actor, action, "Site", target, "FAILURE",
                                           after={"error": str(exc)})
        raise
