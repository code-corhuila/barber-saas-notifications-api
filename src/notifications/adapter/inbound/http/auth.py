"""
Each service validates the token itself (authentication.md, norm 5.3.7): the gateway only checks
that a credential is present, and internal calls never pass through it. Same rules as the Java
services' Rs256Verifier: exactly RS256 with the identity public key, exp and sub required, the
identity issuer, and the role the operation needs.

The audience is checked by route, not by PyJWT (07-api/authentication.md, validation steps 4 and 5):
the routes of the app take only user tokens issued for the app (docs#164), and the internal
operation takes only the worker's token meant for this service with the scope it grants (docs#158,
docs#159). PyJWT alone would refuse every token that carries an `aud`, which every token does.
"""
from dataclasses import dataclass, field
from uuid import UUID

import jwt
from fastapi import Request

from notifications.adapter.inbound.http.errors import ApiError

ISSUER = "barber-saas-identity-auth-api"
USER_ROLES = frozenset({"SUPER_ADMIN", "ADMIN_BARBERSHOP", "BARBER", "CLIENT"})
SERVICE_ROLE = "SERVICE"
LEEWAY_SECONDS = 30
APP_AUDIENCE = "barber-saas-app"
SERVICE_AUDIENCE = "barber-saas-notifications-api"
SERVICE_TOKEN_MAX_SECONDS = 7 * 24 * 3600


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class Caller:
    """Who calls, exactly as the validated token states it."""

    sub: str
    role: str
    barbershop_id: str | None
    audience: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    lifetime_seconds: int | None = None


def _names(aud) -> frozenset[str]:
    """`aud` is one string or a list of strings (RFC 7519, 4.1.3)."""
    if isinstance(aud, str):
        return frozenset({aud})
    if isinstance(aud, list):
        return frozenset(a for a in aud if isinstance(a, str))
    return frozenset()


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
                                options={"require": ["exp", "sub", "iss"], "verify_aud": False})
        except jwt.PyJWTError as error:
            raise InvalidToken(str(error)) from error
        role = claims.get("role")
        if role not in USER_ROLES and role != SERVICE_ROLE:
            raise InvalidToken("unknown role")
        scope = claims.get("scope")
        iat = claims.get("iat")
        return Caller(sub=claims["sub"], role=role, barbershop_id=claims.get("barbershopId"),
                      audience=_names(claims.get("aud")),
                      scopes=frozenset(scope.split()) if isinstance(scope, str) else frozenset(),
                      lifetime_seconds=int(claims["exp"]) - int(iat) if isinstance(iat, (int, float)) else None)


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
    # docs#164: the routes of the app take only user tokens issued for the app; a service token is 401.
    if caller.role == SERVICE_ROLE or APP_AUDIENCE not in caller.audience:
        raise ApiError.unauthorized("The authentication token is not valid")
    if caller.role not in USER_ROLES:
        raise ApiError.forbidden()
    try:
        return UUID(caller.sub)
    except ValueError:
        raise ApiError.unauthorized("The authentication token is not valid") from None


def service(expected_sub: str, scope: str):
    """
    An internal operation: only the service token whose sub is expected, meant for this service
    (`aud`, docs#158), living at most 7 days and granting `scope` (docs#159). Anything else is 403.
    """
    def check(request: Request) -> Caller:
        caller = _caller(request)
        if caller.role != SERVICE_ROLE or caller.sub != expected_sub:
            raise ApiError.forbidden()
        if SERVICE_AUDIENCE not in caller.audience or scope not in caller.scopes:
            raise ApiError.forbidden()
        if caller.lifetime_seconds is None or caller.lifetime_seconds > SERVICE_TOKEN_MAX_SECONDS:
            raise ApiError.forbidden()
        return caller
    return check
