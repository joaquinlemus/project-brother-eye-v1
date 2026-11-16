class DomainError(Exception):
    """Regla de negocio violada (se traduce a HTTP 409/422)."""


class InvalidTransition(DomainError):
    """Transición de estado no permitida para el agregado."""


class IpamExhausted(DomainError):
    """No quedan recursos libres en un pool."""


class ConcurrencyError(DomainError):
    """Otro proceso modificó el agregado (bloqueo optimista)."""


class NotFound(DomainError):
    """El recurso no existe."""


class Forbidden(DomainError):
    """La operación no está permitida para este recurso (p. ej. sitio protegido)."""


class AuthError(DomainError):
    """Credenciales o segundo factor inválidos."""
