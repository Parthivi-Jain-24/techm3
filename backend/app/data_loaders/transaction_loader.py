"""Transaction loader — joins KYC clients to SAML-D accounts.

Source files:
    data/kyc_profiles/client_account_mapping.csv
        Columns: client_id, client_name, account, sector, sanctions_flag, pep_flag
    data/aml_transactions/SAML-D.csv
        Columns: Time, Date, Sender_account, Receiver_account, Amount,
                 Payment_currency, Received_currency, Sender_bank_location,
                 Receiver_bank_location, Payment_type, Is_laundering,
                 Laundering_type

The mapping file links *client_id* → one-or-more *account* numbers.
Transactions reference accounts via Sender_account / Receiver_account.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from app.config import settings

# ── In-memory caches ────────────────────────────────────────────────
_client_accounts: dict[int, set[str]] | None = None
_txns_by_account: dict[str, list[dict]] | None = None


def _load_account_mapping() -> dict[int, set[str]]:
    global _client_accounts
    if _client_accounts is not None:
        return _client_accounts

    path: Path = settings.data_folder / "kyc_profiles" / "client_account_mapping.csv"
    _client_accounts = defaultdict(set)
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cid = int(row["client_id"])
            _client_accounts[cid].add(row["account"].strip())

    return _client_accounts


def _load_transactions() -> dict[str, list[dict]]:
    global _txns_by_account
    if _txns_by_account is not None:
        return _txns_by_account

    path: Path = settings.data_folder / "aml_transactions" / "SAML-D.csv"
    _txns_by_account = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["Amount"] = float(row["Amount"])
            row["Is_laundering"] = int(row["Is_laundering"])
            sender = row["Sender_account"].strip()
            receiver = row["Receiver_account"].strip()
            # Index by both sides so we capture sends AND receives
            _txns_by_account[sender].append(row)
            if receiver != sender:
                _txns_by_account[receiver].append(row)

    return _txns_by_account


# ── Public API ──────────────────────────────────────────────────────

def get_accounts_for_client(client_id: int) -> set[str]:
    """Return the set of account numbers linked to *client_id*."""
    return _load_account_mapping().get(client_id, set())


def get_client_transactions(client_id: int) -> list[dict]:
    """Return every transaction where *client_id* is sender OR receiver.

    Uses the account-mapping table to resolve client → accounts, then
    looks up each account in the pre-indexed SAML-D data.
    """
    accounts = get_accounts_for_client(client_id)
    if not accounts:
        return []

    txn_index = _load_transactions()
    seen_keys: set[tuple] = set()
    results: list[dict] = []

    for acct in accounts:
        for txn in txn_index.get(acct, []):
            # Deduplicate (same txn found via sender AND receiver)
            key = (txn["Date"], txn["Time"], txn["Sender_account"], txn["Receiver_account"], str(txn["Amount"]))
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(txn)

    return results
