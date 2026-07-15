"""Central source-to-canonical mapping and deterministic value normalizers.

Everything that knows about the *shape of the real KYC dataset* lives here, so
column renames and value-normalization rules are explicit, centralized, and
testable — never scattered through the pipeline.

Source schema discovered by inspecting the real challenge dataset
(``clients_with_fatf_ofac.csv``): 2000 rows, 12 columns, already using
snake_case names that match the canonical contract. See docs/kyc-ingestion.md.
"""

from __future__ import annotations

from app.schemas.kyc import SectorRiskLevel

# --------------------------------------------------------------------------- #
# Source -> canonical column mapping
# --------------------------------------------------------------------------- #
# The real dataset already uses canonical names, so most entries are identity
# mappings. Keeping the map explicit means a future dataset with different
# headers only needs a change HERE.
COLUMN_MAP: dict[str, str] = {
    "client_id": "client_id",
    "client_name": "client_name",
    "client_type": "client_type",
    "country": "country",
    "sector": "sector",
    "sector_risk": "sector_risk",
    "pep_flag": "pep_flag",
    "sanctions_flag": "sanctions_flag",
    "fatf_country_flag": "fatf_country_flag",
}

# Source columns required to build a NormalizedKYCEntity. If any is absent the
# file cannot be normalized (SourceSchemaError).
REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = tuple(COLUMN_MAP.keys())

# Canonical fields that must be non-blank after normalization.
REQUIRED_CANONICAL_FIELDS: tuple[str, ...] = (
    "client_id",
    "client_name",
    "client_type",
    "country",
    "sector",
)

# Canonical boolean fields and their source columns.
BOOLEAN_FIELDS: tuple[str, ...] = ("pep_flag", "sanctions_flag", "fatf_country_flag")

# Source columns that exist in the real dataset but are intentionally NOT part
# of the canonical contract yet (candidates for a future coordinated extension).
KNOWN_EXTRA_SOURCE_COLUMNS: tuple[str, ...] = (
    "ofac_country_flag",
    "sectoral_sanctions_flag",
    "ownership_opacity_score",
)

# --------------------------------------------------------------------------- #
# Central field length limits (defense against pathological values)
# --------------------------------------------------------------------------- #
MAX_FIELD_LENGTHS: dict[str, int] = {
    "client_id": 64,
    "client_name": 256,
    "client_type": 64,
    "country": 64,
    "sector": 128,
}

# --------------------------------------------------------------------------- #
# Boolean normalization
# --------------------------------------------------------------------------- #
# Explicit, case-insensitive map. IMPORTANT: we never use bool("false"), which
# is True. Unknown tokens are NOT coerced — they raise ValueError so the caller
# records an `invalid_boolean` issue.
_BOOLEAN_TRUE: frozenset[str] = frozenset({"true", "1", "yes", "y", "t"})
_BOOLEAN_FALSE: frozenset[str] = frozenset({"false", "0", "no", "n", "f"})


def normalize_bool(raw: str) -> bool:
    """Map a known textual boolean to a real bool, else raise ValueError."""
    token = (raw or "").strip().lower()
    if token in _BOOLEAN_TRUE:
        return True
    if token in _BOOLEAN_FALSE:
        return False
    raise ValueError(f"unrecognized boolean value (len={len(token)})")


# --------------------------------------------------------------------------- #
# Sector-risk normalization (categorical: High/Medium/Low)
# --------------------------------------------------------------------------- #
_SECTOR_RISK_MAP: dict[str, SectorRiskLevel] = {
    "low": SectorRiskLevel.LOW,
    "medium": SectorRiskLevel.MEDIUM,
    "med": SectorRiskLevel.MEDIUM,
    "high": SectorRiskLevel.HIGH,
}


def normalize_sector_risk(raw: str) -> SectorRiskLevel:
    """Map a known sector-risk category to the enum, else raise ValueError."""
    token = (raw or "").strip().lower()
    try:
        return _SECTOR_RISK_MAP[token]
    except KeyError:
        raise ValueError(f"unrecognized sector_risk value (len={len(token)})")


# --------------------------------------------------------------------------- #
# String normalization
# --------------------------------------------------------------------------- #
def normalize_whitespace(raw: str) -> str:
    """Trim surrounding whitespace and collapse internal runs to single spaces.

    Conservative: preserves punctuation and semantic content of names.
    """
    return " ".join((raw or "").split())
