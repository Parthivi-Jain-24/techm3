"""Data loaders for sanctions lists, client data, transactions, articles, and UBO structures."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from .schemas import EntityRecord, OwnershipEdge, SanctionedEntity

# OpenSanctions ships single fields larger than csv's 128 KB default.
csv.field_size_limit(10**9)

# Treasury publishes sdn.csv/alt.csv with NO header row; the committed samples
# have one. Both shapes must load, so the column names are declared here and a
# header is detected rather than assumed.
OFAC_SDN_COLUMNS = [
    "ent_num", "SDN_Name", "SDN_Type", "Program", "Title", "Call_Sign",
    "Vess_type", "Tonnage", "GRT", "Vess_flag", "Vess_owner", "Remarks",
]
OFAC_ALT_COLUMNS = ["ent_num", "alt_num", "alt_type", "alt_name", "alt_remarks"]

# OFAC writes this marker instead of leaving a field blank.
OFAC_NULL = "-0-"

# OpenSanctions schemas worth screening a KYC customer against. Vessels,
# aircraft, securities and crypto wallets are not name-screening targets.
KYC_SCHEMAS = frozenset({"Person", "Company", "LegalEntity", "Organization"})


def _clean(value: str | None) -> str | None:
    """Strip a field and fold OFAC's '-0-' null marker to None."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == OFAC_NULL:
        return None
    return cleaned


def _intern(value: str | None) -> str | None:
    """Share one string object across every row carrying the same value.

    Nationality, entity_type and source_list draw from small vocabularies but
    repeat across ~1.3M rows; without interning each row holds its own copy.
    """
    return sys.intern(value) if value else value


def _dict_reader(handle, columns: list[str]) -> csv.DictReader:
    """Build a DictReader that works headerless or headered.

    Detects a header by testing the first cell against the first column name;
    OFAC's ent_num is always numeric, so this cannot misfire on real data.
    Ragged rows (real OFAC has them) fill with '' rather than None.
    """
    first_line = handle.readline()
    handle.seek(0)
    first_cell = first_line.split(",")[0].strip().strip('"').lower()
    if first_cell == columns[0].lower():
        return csv.DictReader(handle, restval="")
    return csv.DictReader(handle, fieldnames=columns, restval="")


# ---------------------------------------------------------------------------
# OFAC SDN loader
# ---------------------------------------------------------------------------

def _parse_remarks(remarks: str) -> dict[str, Any]:
    """Extract DOB, nationality, and aliases from OFAC SDN Remarks field."""
    info: dict[str, Any] = {}

    # DOB patterns: "DOB 15 Mar 1975" or "DOB 1975"
    dob_match = re.search(r"DOB\s+(\d{1,2}\s+\w+\s+\d{4}|\d{4})", remarks, re.IGNORECASE)
    if dob_match:
        info["dob"] = dob_match.group(1).strip()

    # Nationality: "nationality UAE"
    nat_match = re.search(r"nationality\s+([A-Za-z\s]+?)(?:;|$)", remarks, re.IGNORECASE)
    if nat_match:
        info["nationality"] = nat_match.group(1).strip()

    # Inline aliases: "a.k.a. 'NAME'"
    aka_matches = re.findall(r"a\.k\.a\.\s+'([^']+)'", remarks, re.IGNORECASE)
    if aka_matches:
        info["aliases"] = aka_matches

    return info


def _normalize_sdn_name(name: str) -> str:
    """Convert 'LAST, First Middle' to 'First Middle Last'."""
    if "," in name:
        parts = name.split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return name.strip()


def load_ofac_sdn(
    sdn_path: str | Path,
    alt_path: str | Path | None = None,
) -> list[SanctionedEntity]:
    """Parse OFAC SDN CSV + optional ALT CSV into SanctionedEntity objects.

    SDN columns: ent_num,SDN_Name,SDN_Type,Program,Title,Call_Sign,
                 Vess_type,Tonnage,GRT,Vess_flag,Vess_owner,Remarks
    ALT columns: ent_num,alt_num,alt_type,alt_name,alt_remarks
    """
    sdn_path = Path(sdn_path)
    if not sdn_path.exists():
        raise FileNotFoundError(f"SDN file not found: {sdn_path}")

    # Load aliases from ALT file if provided
    aliases_map: dict[str, list[str]] = {}
    if alt_path:
        alt_path = Path(alt_path)
        if alt_path.exists():
            with open(alt_path, encoding="utf-8", errors="replace") as f:
                for row in _dict_reader(f, OFAC_ALT_COLUMNS):
                    ent_num = _clean(row.get("ent_num"))
                    alt_name = _clean(row.get("alt_name"))
                    if ent_num and alt_name:
                        aliases_map.setdefault(ent_num, []).append(alt_name)

    entities: list[SanctionedEntity] = []
    with open(sdn_path, encoding="utf-8", errors="replace") as f:
        for row in _dict_reader(f, OFAC_SDN_COLUMNS):
            ent_num = _clean(row.get("ent_num"))
            sdn_name = _clean(row.get("SDN_Name"))
            if not ent_num or not sdn_name:
                continue

            remarks = _clean(row.get("Remarks")) or ""
            title = _clean(row.get("Title")) or ""
            parsed = _parse_remarks(remarks)

            # Combine aliases from ALT file + inline Remarks aliases
            all_aliases = list(aliases_map.get(ent_num, []))
            for aka in parsed.get("aliases", []):
                if aka not in all_aliases:
                    all_aliases.append(aka)

            sdn_type = (_clean(row.get("SDN_Type")) or "").lower()
            entity_type = "individual" if sdn_type == "individual" else "entity"
            program = _clean(row.get("Program"))

            entities.append(SanctionedEntity(
                entity_id=f"OFAC_SDN_{ent_num.zfill(6)}",
                name=_normalize_sdn_name(sdn_name),
                aliases=all_aliases,
                dob=parsed.get("dob"),
                nationality=_intern(parsed.get("nationality")),
                entity_type=_intern(entity_type),
                company=None,
                topics=[_intern(program)] if program else [],
                source_list=_intern("OFAC SDN"),
                source_url=_intern("https://www.treasury.gov/ofac/downloads/sdn.csv"),
                context=f"{title} {remarks}".strip() or None,
            ))

    return entities


# ---------------------------------------------------------------------------
# OpenSanctions loader
# ---------------------------------------------------------------------------

def opensanctions_url(entity_id: str) -> str:
    """The public page for an OpenSanctions entity.

    Derived on demand rather than stored: ~1.3M unique URLs cost ~120 MB to keep
    around, and every one of them is this f-string.
    """
    return f"https://opensanctions.org/entities/{entity_id}/"

def load_opensanctions(
    csv_path: str | Path,
    limit: int | None = None,
    schemas: frozenset[str] | None = KYC_SCHEMAS,
) -> list[SanctionedEntity]:
    """Parse OpenSanctions simple CSV into SanctionedEntity objects.

    Multi-value fields use semicolon (;) as separator.

    The real targets.simple.csv is ~1.32M rows / 488 MB. Loading all of it
    measures ~16s and ~0.8 GB of models (~1.1 GB once indexed). `limit` caps the
    number of entities returned; `schemas` filters to the types worth
    name-screening, which drops ~44k vessels, aircraft, securities and crypto
    wallets (pass None to keep every schema).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"OpenSanctions file not found: {csv_path}")

    entities: list[SanctionedEntity] = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if limit is not None and len(entities) >= limit:
                break

            entity_id = (row.get("id") or "").strip()
            name = (row.get("name") or "").strip()
            if not entity_id or not name:
                continue

            schema = (row.get("schema", "") or "").strip()
            if schemas is not None and schema not in schemas:
                continue
            entity_type = "individual" if schema == "Person" else "entity"

            aliases_raw = (row.get("aliases", "") or "").strip()
            aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()] if aliases_raw else []

            countries_raw = (row.get("countries", "") or "").strip()
            nationality = countries_raw.split(";")[0].strip().upper() if countries_raw else None

            dob = (row.get("birth_date", "") or "").strip() or None
            sanctions = (row.get("sanctions", "") or "").strip()
            dataset = (row.get("dataset", "") or "").strip()

            entities.append(SanctionedEntity(
                entity_id=entity_id,
                name=name,
                aliases=aliases,
                dob=dob,
                nationality=_intern(nationality),
                entity_type=_intern(entity_type),
                company=None,
                topics=[s.strip() for s in sanctions.split(";") if s.strip()] if sanctions else [],
                source_list=_intern(dataset or "opensanctions"),
                # Derivable from entity_id; storing ~1.3M unique URLs costs
                # ~120 MB for a string nothing reads. See opensanctions_url().
                source_url=None,
                # No descriptive context: targets.simple.csv has no notes/summary
                # column. The `sanctions` field is list-membership metadata
                # ("OFAC SDN - SDGT", "Reciprocal - Active - 2019-12-10"), not a
                # description of what the entity does — it already populates
                # `topics`. Scoring it as context penalised true matches for
                # having no description (0.085 against a role summary) instead of
                # staying neutral at the 0.3 "unknown context" default.
                context=None,
            ))

    return entities


# ---------------------------------------------------------------------------
# Client data loader (your dataset)
# ---------------------------------------------------------------------------

def load_clients(csv_path: str | Path) -> list[dict[str, Any]]:
    """Load client KYC data from clients_with_fatf_ofac.csv.

    Returns raw dicts suitable for feeding into the entity resolution pipeline.
    Each dict contains: client_id, client_name, client_type, sector, sector_risk,
    country, pep_flag, sanctions_flag, fatf_country_flag, ofac_country_flag,
    sectoral_sanctions_flag, ownership_opacity_score.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Client file not found: {csv_path}")

    clients: list[dict[str, Any]] = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clients.append({
                "entity_id": f"CLIENT-{row['client_id']}",
                "name": row.get("client_name", "").strip(),
                "client_type": row.get("client_type", "").strip(),
                "sector": row.get("sector", "").strip(),
                "sector_risk": row.get("sector_risk", "").strip(),
                "country": row.get("country", "").strip(),
                "nationality": row.get("country", "").strip(),
                "company": row.get("client_name", "").strip(),
                "context": f"{row.get('client_type', '')} in {row.get('sector', '')} sector, based in {row.get('country', '')}",
                "pep_flag": int(row.get("pep_flag", 0)),
                "sanctions_flag": int(row.get("sanctions_flag", 0)),
                "fatf_country_flag": int(row.get("fatf_country_flag", 0)),
                "ofac_country_flag": int(row.get("ofac_country_flag", 0)),
                "sectoral_sanctions_flag": int(row.get("sectoral_sanctions_flag", 0)),
                "ownership_opacity_score": float(row.get("ownership_opacity_score", 0)),
            })

    return clients


# ---------------------------------------------------------------------------
# Transactions loader (your dataset)
# ---------------------------------------------------------------------------

def load_transactions(csv_path: str | Path) -> list[dict[str, Any]]:
    """Load transaction data from transactions_with_fatf_ofac.csv.

    Returns raw dicts with all transaction fields including risk flags.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Transaction file not found: {csv_path}")

    transactions: list[dict[str, Any]] = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append({
                "transaction_id": row.get("transaction_id", "").strip(),
                "client_id": f"CLIENT-{row.get('client_id', '').strip()}",
                "amount": float(row.get("amount", 0)),
                "transaction_type": row.get("transaction_type", "").strip(),
                "timestamp": row.get("timestamp", "").strip(),
                "client_country": row.get("client_country", "").strip(),
                "counterparty_country": row.get("counterparty_country", "").strip(),
                "ofac_match_flag": int(row.get("ofac_match_flag", 0)),
                "fatf_country_flag": int(row.get("fatf_country_flag", 0)),
                "structuring_pattern_flag": int(row.get("structuring_pattern_flag", 0)),
                "rapid_movement_flag": int(row.get("rapid_movement_flag", 0)),
                "trade_mispricing_flag": int(row.get("trade_mispricing_flag", 0)),
            })

    return transactions


# ---------------------------------------------------------------------------
# UBO ownership structure loader
# ---------------------------------------------------------------------------

def load_ubo_structure(json_path: str | Path) -> tuple[list[EntityRecord], list[OwnershipEdge]]:
    """Parse a UBO structure JSON file into entities and ownership edges."""
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"UBO structure file not found: {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    entities = [
        EntityRecord(
            entity_id=e["entity_id"],
            name=e["name"],
            context=e.get("context"),
            metadata={k: v for k, v in e.items() if k not in ("entity_id", "name", "context")},
        )
        for e in data.get("entities", [])
    ]

    edges = [
        OwnershipEdge(
            owner_id=edge["owner_id"],
            owned_id=edge["owned_id"],
            percentage=edge.get("percentage"),
        )
        for edge in data.get("ownership_edges", [])
    ]

    return entities, edges


# ---------------------------------------------------------------------------
# Articles loader
# ---------------------------------------------------------------------------

def load_articles(directory: str | Path) -> list[dict[str, str]]:
    """Load all .txt articles from a directory.

    Returns list of {'filename': str, 'content': str} dicts.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Articles directory not found: {directory}")

    articles = []
    for txt_file in sorted(directory.glob("*.txt")):
        articles.append({
            "filename": txt_file.name,
            "content": txt_file.read_text(encoding="utf-8", errors="replace"),
        })

    return articles


# ---------------------------------------------------------------------------
# GDPR data loader (your dataset)
# ---------------------------------------------------------------------------

def load_gdpr_articles(csv_path: str | Path) -> list[dict[str, str]]:
    """Load GDPR articles for compliance reference.

    Returns list of dicts with article_id, article_title, article_text, article_recitals.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"GDPR articles file not found: {csv_path}")

    articles = []
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            articles.append({
                "article_id": row.get("article_id", "").strip(),
                "article_title": row.get("article_title", "").strip(),
                "article_text": row.get("article_text", "").strip(),
                "article_recitals": row.get("article_recitals", "").strip(),
            })

    return articles
