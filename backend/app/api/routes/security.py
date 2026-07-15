"""Protected demonstration endpoints proving authentication + RBAC.

No real KYC data is exposed here (no public KYC / ingestion endpoint — that is
Phase 5). These endpoints only prove the security boundary works.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.identity.authentication.dependencies import get_current_principal
from app.identity.authentication.models import Principal, SafePrincipalView
from app.identity.authorization.dependencies import require_permission
from app.identity.authorization.permissions import Permission

router = APIRouter()


@router.get("/me", response_model=SafePrincipalView)
def read_me(principal: Principal = Depends(get_current_principal)) -> SafePrincipalView:
    """Return a client-safe view of the authenticated principal.

    Never returns passwords, hashes, tokens, or secrets.
    """
    return SafePrincipalView.from_principal(principal)


@router.get("/data-quality-access-check")
def data_quality_access_check(
    principal: Principal = Depends(require_permission(Permission.DATA_QUALITY_READ)),
) -> dict:
    """Permission-protected demo: requires DATA_QUALITY_READ. Returns only a
    safe authorization confirmation, not any dataset content."""
    return {
        "status": "authorized",
        "required_permission": Permission.DATA_QUALITY_READ.value,
        "principal_id": principal.principal_id,
        "principal_type": principal.principal_type.value,
    }
