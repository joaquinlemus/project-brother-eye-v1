"""Primitivas de seguridad: Argon2id, TOTP (RFC 6238), cifrado del secreto MFA y tokens firmados."""
from __future__ import annotations

import base64
import hashlib
import io
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pyotp
import segno
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_ph = PasswordHasher()   # Argon2id con parámetros por defecto (RFC 9106, perfil de baja memoria)
_DUMMY_HASH = _ph.hash("tiempo-constante")

MIN_PASSWORD = 10


def hash_password(password: str) -> str:
    validate_password(password)
    return _ph.hash(password)


def validate_password(password: str) -> None:
    from app.domain.errors import DomainError
    if len(password) < MIN_PASSWORD:
        raise DomainError(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
    if password.isdigit() or password.isalpha():
        raise DomainError("La contraseña debe combinar letras y números o símbolos")


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        # Si el usuario no existe se verifica contra un hash ficticio: mismo tiempo de respuesta
        return _ph.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


# ------------------------------------------------------------------------------- MFA (TOTP)
def _fernet() -> Fernet:
    key = hashlib.sha256(("mfa:" + settings.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def totp_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=settings.mfa_issuer)


def qr_svg(data: str) -> str:
    buf = io.BytesIO()
    # omitsize=True: el SVG lleva viewBox y escala al tamaño que le dé la página (sin viewBox el
    # navegador lo recortaba y la cámara no encontraba las esquinas). border=4: zona blanca estándar.
    segno.make(data, error="m").save(buf, kind="svg", scale=5, border=4, xmldecl=False,
                                     omitsize=True, dark="#000000", light="#ffffff")
    return buf.getvalue().decode()


def verify_totp(secret: str, code: str, last_step: int | None) -> int | None:
    """Devuelve el paso de tiempo aceptado, o None. Tolera ±30 s y rechaza códigos reutilizados."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // 30
    for step in (now_step - 1, now_step, now_step + 1):
        if totp.at(step * 30) == code and (last_step is None or step > last_step):
            return step
    return None


# ------------------------------------------------------------------------------- tokens
ALG = "HS256"


def make_token(user_id: UUID, stage: str, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "stage": stage, "iat": now,
               "exp": now + timedelta(minutes=minutes), "iss": "portal-heladeria"}
    return jwt.encode(payload, settings.secret_key, algorithm=ALG)


def read_token(token: str, stage: str) -> UUID | None:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALG], issuer="portal-heladeria")
    except jwt.PyJWTError:
        return None
    if data.get("stage") != stage:
        return None
    try:
        return UUID(data["sub"])
    except (KeyError, ValueError):
        return None
