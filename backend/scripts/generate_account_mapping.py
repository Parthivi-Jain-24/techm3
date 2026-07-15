"""Regenerate data/kyc_profiles/client_account_mapping.csv.

The transaction loader joins KYC clients to SAML-D transactions through this
file (`client_id,account`). It is a *derived demo fixture*: SAML-D account
numbers are synthetic and carry no real link to the synthetic KYC clients, so
the original TMCode2 team generated a mapping — but the file itself was never
committed (the repo gitignores `*.csv`), which breaks the investigation
pipeline on a fresh clone with FileNotFoundError.

This script rebuilds it deterministically (sorted inputs, no randomness) so
every machine derives the same file:

  * Clients flagged high-risk in the KYC data (sanctions_flag / ofac_country_flag)
    are mapped to accounts that appear in laundering-flagged SAML-D rows — the
    investigation demo needs risky clients to actually have risky transactions.
  * A spread of unflagged clients get clean accounts, as the control group.

Run from backend/:  python scripts/generate_account_mapping.py
"""

from __future__ import annotations

import csv
from itertools import islice
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA = BACKEND_ROOT.parent / "data"
CLIENTS_CSV = DATA / "kyc_profiles" / "clients_with_fatf_ofac.csv"
SAML_CSV = DATA / "aml_transactions" / "SAML-D.csv"
OUT = DATA / "kyc_profiles" / "client_account_mapping.csv"

# Sized to the original fixture's documented shape (~122 rows).
FLAGGED_CLIENTS = 30
CLEAN_CLIENTS = 30
ACCOUNTS_PER_CLIENT = 2


def _accounts(max_scan: int = 400_000) -> tuple[list[str], list[str]]:
    """First-seen laundering and clean sender accounts, in file order.

    Scanning a bounded prefix keeps this fast on the 9.5M-row file while still
    yielding far more distinct accounts than the mapping needs.
    """
    laundering: dict[str, None] = {}
    clean: dict[str, None] = {}
    with open(SAML_CSV, newline="", encoding="utf-8") as fh:
        for row in islice(csv.DictReader(fh), max_scan):
            bucket = laundering if row["Is_laundering"] == "1" else clean
            bucket.setdefault(row["Sender_account"].strip())
            if len(laundering) >= 200 and len(clean) >= 200:
                break
    return list(laundering), list(clean)


def _clients() -> tuple[list[int], list[int]]:
    """Client ids split into (high-risk-flagged, unflagged), ascending."""
    flagged: list[int] = []
    unflagged: list[int] = []
    with open(CLIENTS_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cid = int(row["client_id"])
            risky = row.get("sanctions_flag") == "1" or row.get("ofac_country_flag") == "1"
            (flagged if risky else unflagged).append(cid)
    return sorted(flagged), sorted(unflagged)


def main() -> None:
    laundering_accounts, clean_accounts = _accounts()
    flagged, unflagged = _clients()

    rows: list[tuple[int, str]] = []
    li = ci = 0
    for cid in flagged[:FLAGGED_CLIENTS]:
        for _ in range(ACCOUNTS_PER_CLIENT):
            rows.append((cid, laundering_accounts[li % len(laundering_accounts)]))
            li += 1
    for cid in unflagged[:CLEAN_CLIENTS]:
        for _ in range(ACCOUNTS_PER_CLIENT):
            rows.append((cid, clean_accounts[ci % len(clean_accounts)]))
            ci += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["client_id", "account"])
        writer.writerows(rows)

    print(f"wrote {len(rows)} mappings -> {OUT}")
    print(f"  flagged clients : {min(FLAGGED_CLIENTS, len(flagged))} (laundering-linked accounts)")
    print(f"  clean clients   : {min(CLEAN_CLIENTS, len(unflagged))} (clean accounts)")


if __name__ == "__main__":
    main()
