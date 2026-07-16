"""Authentication, authorization, validation, and immutable audit helpers."""

import re
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import API_TOKENS, AUTH_REQUIRED
from app.core.persistence import workflow_store

_bearer = HTTPBearer(auto_error=False)
_SECRET_KEYS = re.compile(r"(token|secret|password|authorization|api[_-]?key)", re.I)


@dataclass(frozen=True)
class Principal:
    actor_id: str
    roles: frozenset[str]


def current_principal(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    if not AUTH_REQUIRED:
        return Principal(actor_id="anonymous", roles=frozenset())
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail={"error_code": "AUTHENTICATION_REQUIRED"})
    record = API_TOKENS.get(credentials.credentials)
    if not record or not record.get("actor_id"):
        raise HTTPException(status_code=401, detail={"error_code": "INVALID_CREDENTIALS"})
    return Principal(actor_id=str(record["actor_id"]), roles=frozenset(record.get("roles", [])))


def enforce_owner(principal: Principal, owner_id: str) -> None:
    if principal.actor_id != owner_id and not principal.roles.intersection({"reviewer", "override", "admin"}):
        raise HTTPException(status_code=403, detail={"error_code": "SIMULATION_OWNERSHIP_REQUIRED"})


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEYS.search(key) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def audit_event(event_type: str, *, actor_id: str, request_id: str | None = None,
                simulation_id: str | None = None, details: dict[str, Any] | None = None) -> None:
    workflow_store.append_audit_record(
        event_type=event_type, actor_id=actor_id, request_id=request_id,
        simulation_id=simulation_id, details=redact(details or {}),
    )


class A2AAuthMiddleware(BaseHTTPMiddleware):
    """Apply the same bearer-token policy to ADK-generated A2A apps."""
    async def dispatch(self, request, call_next):
        if not AUTH_REQUIRED:
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or token not in API_TOKENS:
            return JSONResponse(status_code=401, content={"detail": {"error_code": "AUTHENTICATION_REQUIRED"}})
        return await call_next(request)
