from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.api.deps import Principal, audit_for, require
from app.application import security as sec
from app.db import tx
from app.domain.errors import DomainError, NotFound
from app.infrastructure.repos import UserRepo

router = APIRouter(tags=["usuarios"])


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,32}$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    full_name: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    roles: list[str] = Field(min_length=1)


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=80)
    is_active: bool | None = None
    roles: list[str] | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=256)


@router.get("/roles")
def roles(_: Principal = Depends(require("site:read"))) -> list[dict]:
    with tx() as conn:
        return UserRepo(conn).roles()


@router.get("/users")
def list_users(_: Principal = Depends(require("user:admin"))) -> list[dict]:
    with tx() as conn:
        return UserRepo(conn).list()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request,
                p: Principal = Depends(require("user:admin"))) -> dict:
    with tx() as conn:
        users = UserRepo(conn)
        uid = users.create(body.username, body.email, body.full_name, sec.hash_password(body.password))
        users.set_roles(uid, body.roles)
        audit_for(request, conn).write(p.user_id, "user.create", "User", str(uid), "SUCCESS",
                                       after={"username": body.username, "roles": body.roles})
        return users.public(uid)


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, body: UserPatch, request: Request,
                p: Principal = Depends(require("user:admin"))) -> dict:
    with tx() as conn:
        users = UserRepo(conn)
        before = users.public(user_id)
        if before is None or before["username"] == "system":
            raise NotFound("El usuario no existe")
        if user_id == p.user_id and (body.is_active is False or
                                     (body.roles is not None and "admin" not in body.roles)):
            raise DomainError("No puedes desactivarte ni quitarte el rol de administrador")
        fields = body.model_dump(exclude_none=True, exclude={"roles"})
        users.update(user_id, **fields)
        if body.roles is not None:
            users.set_roles(user_id, body.roles)
        after = users.public(user_id)
        audit_for(request, conn).write(p.user_id, "user.update", "User", str(user_id), "SUCCESS",
                                       before={"roles": before["roles"], "active": before["is_active"]},
                                       after={"roles": after["roles"], "active": after["is_active"]})
        return after


@router.post("/users/{user_id}/reset-mfa", summary="El usuario volverá a escanear el QR")
def reset_mfa(user_id: UUID, request: Request, p: Principal = Depends(require("user:admin"))) -> dict:
    with tx() as conn:
        users = UserRepo(conn)
        if users.public(user_id) is None:
            raise NotFound("El usuario no existe")
        users.update(user_id, mfa_enabled=False, mfa_secret_enc=None, mfa_last_step=None)
        audit_for(request, conn).write(p.user_id, "user.reset_mfa", "User", str(user_id), "SUCCESS")
    return {"ok": True}


@router.post("/users/{user_id}/password", summary="Asignar contraseña temporal y desbloquear")
def set_password(user_id: UUID, body: PasswordReset, request: Request,
                 p: Principal = Depends(require("user:admin"))) -> dict:
    from datetime import UTC, datetime
    with tx() as conn:
        users = UserRepo(conn)
        if users.public(user_id) is None:
            raise NotFound("El usuario no existe")
        users.update(user_id, password_hash=sec.hash_password(body.password), failed_logins=0,
                     locked_until=None, password_changed_at=datetime.now(UTC))
        audit_for(request, conn).write(p.user_id, "user.password_reset", "User", str(user_id),
                                       "SUCCESS")
    return {"ok": True}
