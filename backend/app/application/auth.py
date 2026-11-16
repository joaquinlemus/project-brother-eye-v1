"""Casos de uso de autenticación: contraseña -> segundo factor (TOTP) obligatorio."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg import Connection

from app.application import security as sec
from app.domain.errors import AuthError
from app.infrastructure.repos import AuditRepo, UserRepo

LOCK_AFTER = 5          # intentos fallidos (contraseña o código) antes de bloquear
LOCK_MINUTES = 15
MFA_TOKEN_MINUTES = 5


def _register_failure(users: UserRepo, u: dict) -> None:
    failed = (u["failed_logins"] or 0) + 1
    fields: dict = {"failed_logins": failed}
    if failed >= LOCK_AFTER:
        fields.update(failed_logins=0, locked_until=datetime.now(UTC) + timedelta(minutes=LOCK_MINUTES))
    users.update(u["id"], **fields)


def _check_lock(u: dict) -> None:
    if u["locked_until"] and u["locked_until"] > datetime.now(UTC):
        mins = int((u["locked_until"] - datetime.now(UTC)).total_seconds() // 60) + 1
        raise AuthError(f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {mins} min.")


def login(conn: Connection, audit: AuditRepo, username: str, password: str) -> dict:
    users = UserRepo(conn)
    u = users.by_username(username.strip().lower())
    if u:
        try:
            _check_lock(u)
        except AuthError:
            audit.write(u["id"], "auth.login", "User", str(u["id"]), "DENIED", after={"reason": "bloqueada"})
            raise
    ok = sec.verify_password(u["password_hash"] if u else None, password) and bool(u and u["is_active"])
    if not ok:
        if u:
            _register_failure(users, u)
        audit.write(u["id"] if u else None, "auth.login", "User", username[:40], "FAILURE",
                    after={"reason": "credenciales"})
        raise AuthError("Usuario o contraseña incorrectos")

    users.update(u["id"], failed_logins=0)
    mfa_token = sec.make_token(u["id"], "mfa", MFA_TOKEN_MINUTES)
    if u["mfa_enabled"] and u["mfa_secret_enc"]:
        return {"status": "MFA_REQUIRED", "mfa_token": mfa_token}

    # Primer ingreso: se genera el secreto y queda pendiente hasta validar un código
    secret = sec.new_totp_secret()
    users.update(u["id"], mfa_secret_enc=sec.encrypt_secret(secret), mfa_last_step=None)
    uri = sec.totp_uri(secret, u["username"])
    return {"status": "MFA_SETUP_REQUIRED", "mfa_token": mfa_token, "otpauth_uri": uri,
            "secret": secret, "qr_svg": sec.qr_svg(uri)}


def verify_mfa(conn: Connection, audit: AuditRepo, mfa_token: str, code: str) -> UUID:
    user_id = sec.read_token(mfa_token, "mfa")
    if user_id is None:
        raise AuthError("La verificación expiró. Vuelve a ingresar tu usuario y contraseña.")
    users = UserRepo(conn)
    u = users.by_id(user_id)
    if not u or not u["is_active"] or not u["mfa_secret_enc"]:
        raise AuthError("La verificación expiró. Vuelve a ingresar tu usuario y contraseña.")
    _check_lock(u)
    secret = sec.decrypt_secret(u["mfa_secret_enc"])
    step = sec.verify_totp(secret, code, u["mfa_last_step"]) if secret else None
    if step is None:
        _register_failure(users, u)
        audit.write(u["id"], "auth.mfa", "User", str(u["id"]), "FAILURE")
        raise AuthError("Código incorrecto o ya utilizado. Espera el siguiente código de 6 dígitos.")
    first_time = not u["mfa_enabled"]
    users.update(u["id"], mfa_last_step=step, mfa_enabled=True, failed_logins=0,
                 last_login_at=datetime.now(UTC))
    if first_time:
        audit.write(u["id"], "auth.mfa.enroll", "User", str(u["id"]), "SUCCESS")
    audit.write(u["id"], "auth.login", "User", str(u["id"]), "SUCCESS")
    return u["id"]
