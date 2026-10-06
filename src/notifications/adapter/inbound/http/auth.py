"""
Each service validates the token itself (authentication.md, norm 5.3.7): the gateway only checks
that a credential is present, and internal calls never pass through it. Same rules as the Java
services' Rs256Verifier: exactly RS256 with the identity public key, exp and sub required, the
identity issuer, and the role the operation needs.
"""
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Request

from notifications.adapter.inbound.http.errors import ApiError

ISSUER = "barber-saas-identity-auth-api"
USER_ROLES = frozenset({"SUPER_ADMIN", "ADMIN_BARBERSHOP", "BARBER", "CLIENT"})
SERVICE_ROLE = "SERVICE"
LEEWAY_SECONDS = 30


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class Caller:
    """Who calls, exactly as the validated token states it."""

    sub: str
    role: str
    barbershop_id: str | None


class Rs256Verifier:
    def __init__(self, public_key_pem: str) -> None:
        # The variable carries the PEM in one line with \n escapes (.env.example).
        pem = public_key_pem.replace("\\n", "\n")
        if "BEGIN PUBLIC KEY" not in pem:
            raise ValueError("JWT_PUBLIC_KEY is not a PEM public key")
        self._key = pem

    def verify(self, token: str) -> Caller:
        try:
            # A closed rule: "none", HS256 or anything else is refused before checking a signature.
            if jwt.get_unverified_header(token).get("alg") != "RS256":
                raise InvalidToken("algorithm not allowed")
            claims = jwt.decode(token, self._key, algorithms=["RS256"], issuer=ISSUER, leeway=LEEWAY_SECONDS,
                                options={"require": ["exp", "sub", "iss"]})
        except jwt.PyJWTError as error:
            raise InvalidToken(str(error)) from error
        role = claims.get("role")
        if role not in USER_ROLES and role != SERVICE_ROLE:
            raise InvalidToken("unknown role")
        return Caller(sub=claims["sub"], role=role, barbershop_id=claims.get("barbershopId"))


def _caller(request: Request) -> Caller:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError.unauthorized("Authentication token required")
    try:
        return request.app.state.verifier.verify(token)
    except InvalidToken:
        raise ApiError.unauthorized("The authentication token is not valid") from None


def current_user(request: Request) -> UUID:
    """A user of any role: their id, the only key of their inbox. A service has no inbox."""
    caller = _caller(request)
    if caller.role not in USER_ROLES:
        raise ApiError.forbidden()
    try:
        return UUID(caller.sub)
    except ValueError:
        raise ApiError.unauthorized("The authentication token is not valid") from None


def service(expected_sub: str):
    """An internal operation: only the service token whose sub is expected; a user's token is 403."""
    def check(request: Request) -> Caller:
        caller = _caller(request)
        if caller.role != SERVICE_ROLE or caller.sub != expected_sub:
            raise ApiError.forbidden()
        return caller
    return check
