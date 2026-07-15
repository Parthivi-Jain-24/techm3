"""KYC client profile loader.

Source file: data/kyc_profiles/clients_with_fatf_ofac.csv
Columns:
    client_id, client_name, client_type, sector, sector_risk, country,
    pep_flag, sanctions_flag, fatf_country_flag, ofac_country_flag,
    sectoral_sanctions_flag, ownership_opacity_score
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.config import settings

# ── In-memory cache (populated once on first access) ────────────────
_clients_by_id: dict[int, dict] | None = None


def _load() -> dict[int, dict]:
    global _clients_by_id
    if _clients_by_id is not None:
        return _clients_by_id

    path: Path = settings.data_folder / "kyc_profiles" / "clients_with_fatf_ofac.csv"
    _clients_by_id = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cid = int(row["client_id"])
            # Coerce numeric fields
            row["client_id"] = cid
            for flag in (
                "pep_flag",
                "sanctions_flag",
                "fatf_country_flag",
                "ofac_country_flag",
                "sectoral_sanctions_flag",
            ):
                row[flag] = int(row[flag])
            row["ownership_opacity_score"] = float(row["ownership_opacity_score"])
            _clients_by_id[cid] = row

    return _clients_by_id


# ── Public API ──────────────────────────────────────────────────────

def get_client_profile(client_id: int) -> dict | None:
    """Return the full KYC profile dict for *client_id*, or ``None``."""
    return _load().get(client_id)


def list_all_client_ids() -> list[int]:
    """Return every known client_id (useful for batch jobs)."""
    return list(_load().keys())
