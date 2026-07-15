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

_SYNTHETIC_CLIENTS = [
    {
        "client_id": 2041,
        "client_name": "Aster Global Holdings",
        "client_type": "Corporate",
        "sector": "Trade Finance",
        "sector_risk": "High",
        "country": "UAE",
        "pep_flag": 1,
        "sanctions_flag": 1,
        "fatf_country_flag": 1,
        "ofac_country_flag": 0,
        "sectoral_sanctions_flag": 1,
        "ownership_opacity_score": 0.82,
    },
    {
        "client_id": 117,
        "client_name": "BlueRiver Manufacturing Ltd",
        "client_type": "Corporate",
        "sector": "Manufacturing",
        "sector_risk": "Medium",
        "country": "India",
        "pep_flag": 0,
        "sanctions_flag": 0,
        "fatf_country_flag": 0,
        "ofac_country_flag": 0,
        "sectoral_sanctions_flag": 0,
        "ownership_opacity_score": 0.21,
    },
    {
        "client_id": 892,
        "client_name": "Northstar Commodities SA",
        "client_type": "Corporate",
        "sector": "Commodities",
        "sector_risk": "High",
        "country": "Panama",
        "pep_flag": 0,
        "sanctions_flag": 0,
        "fatf_country_flag": 1,
        "ofac_country_flag": 0,
        "sectoral_sanctions_flag": 0,
        "ownership_opacity_score": 0.67,
    },
]

# In-memory cache populated once on first access.
_clients_by_id: dict[int, dict] | None = None


def _synthetic_clients() -> dict[int, dict]:
    return {int(row["client_id"]): dict(row) for row in _SYNTHETIC_CLIENTS}


def _load() -> dict[int, dict]:
    global _clients_by_id
    if _clients_by_id is not None:
        return _clients_by_id

    path: Path = settings.data_folder / "kyc_profiles" / "clients_with_fatf_ofac.csv"
    if not path.exists():
        _clients_by_id = _synthetic_clients()
        return _clients_by_id

    _clients_by_id = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cid = int(row["client_id"])
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


def get_client_profile(client_id: int) -> dict | None:
    """Return the full KYC profile dict for *client_id*, or ``None``."""
    return _load().get(client_id)


def list_all_client_ids() -> list[int]:
    """Return every known client_id (useful for batch jobs)."""
    return list(_load().keys())
