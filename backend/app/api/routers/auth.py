from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Principal, clear_session, current_user, run_keep_audit, set_session
from app.application import auth as uc
from app.application import security as sec
from app.db import tx
from app.domain.errors import AuthError
from app.infrastructure.repos import UserRepo

router = APIRouter(prefix="/auth", tags=["autenticación"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/login", summary="Paso 1: usuario y contraseña")
def login(body: LoginIn, request: Request) -> dict:
    return run_keep_audit(request, lambda c, a: uc.login(c, a, body.username, body.password))


@router.post("/mfa", summary="Paso 2: código TOTP (también confirma el enrolamiento)")
def mfa(body: MfaIn, request: Request, response: Response) -> dict:
    user_id = run_keep_audit(request, lambda c, a: uc.verify_mfa(c, a, body.mfa_token, body.code))
    set_session(response, user_id)
    with tx() as conn:
        u = UserRepo(conn).public(user_id)
    return {"user": {"username": u["username"], "full_name": u["full_name"], "roles": u["roles"]}}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(p: Principal = Depends(current_user)) -> dict:
    return {"id": p.user_id, "username": p.username, "full_name": p.full_name,
            "roles": p.roles, "permissions": sorted(p.permissions)}


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordIn, request: Request,
                    p: Principal = Depends(current_user)) -> Response:
    def _do(conn, audit):
        users = UserRepo(conn)
        u = users.by_id(p.user_id)
        if not sec.verify_password(u["password_hash"], body.current_password):
            audit.write(p.user_id, "auth.password", "User", str(p.user_id), "FAILURE")
            raise AuthError("La contraseña actual no es correcta")
        users.update(p.user_id, password_hash=sec.hash_password(body.new_password),
                     password_changed_at=datetime.now(UTC))
        audit.write(p.user_id, "auth.password", "User", str(p.user_id), "SUCCESS")
    run_keep_audit(request, _do)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
