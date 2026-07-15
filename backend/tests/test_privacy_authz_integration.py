"""Phase 4 tests: authorization integrates with (does not bypass) Phase 3 privacy.

Authorization decides WHETHER an operation is allowed and WHICH representation
context is appropriate; the Phase 3 privacy layer decides the actual masked/
minimized representation. Masking logic is not duplicated in the identity layer.
"""

from __future__ import annotations

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.authorization.policies import kyc_context_for
from app.identity.rbac.roles import Role
from app.privacy.contexts import ProcessingContext
from app.privacy.minimization import minimize_kyc_entity
from app.schemas.kyc import NormalizedKYCEntity


def _entity() -> NormalizedKYCEntity:
    return NormalizedKYCEntity(
        client_id="123456", client_name="John Smith", client_type="Individual",
        country="IN", sector="Tech", sector_risk="high",
        pep_flag=True, aliases=["Johnny S"],
    )


def _principal(*roles: Role) -> Principal:
    return Principal(principal_id="P", principal_type=PrincipalType.USER, roles=list(roles))


def test_kyc_read_only_does_not_bypass_minimization() -> None:  # 47
    # COMPLIANCE_REVIEWER has KYC_READ but NOT KYC_VIEW_SENSITIVE.
    ctx = kyc_context_for(_principal(Role.COMPLIANCE_REVIEWER))
    assert ctx is not ProcessingContext.INTERNAL_PROCESSING
    view = minimize_kyc_entity(_entity(), ctx, pseudonymize_key="k")
    # Direct identity is masked, not raw.
    assert view.get("client_name") != "John Smith"


def test_view_sensitive_is_distinct_from_read() -> None:  # 48
    read_ctx = kyc_context_for(_principal(Role.COMPLIANCE_REVIEWER))     # KYC_READ
    sensitive_ctx = kyc_context_for(_principal(Role.COMPLIANCE_ANALYST))  # + VIEW_SENSITIVE
    assert read_ctx is not sensitive_ctx
    assert sensitive_ctx is ProcessingContext.INTERNAL_PROCESSING


def test_authz_layer_does_not_duplicate_masking() -> None:  # 50
    # The policies module must delegate representation to privacy, not mask itself.
    import app.identity.authorization.policies as policies

    src = __import__("inspect").getsource(policies)
    assert "mask_name" not in src and "pseudonymize" not in src and "redact" not in src


def test_context_selection_is_deterministic() -> None:
    p = _principal(Role.COMPLIANCE_ANALYST)
    assert kyc_context_for(p) is kyc_context_for(p)
