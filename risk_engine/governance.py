from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from risk_engine import RiskEngine
from risk_engine.data_repository import DatasetRepository, flag, float_or_zero
from risk_engine.news_service import NewsService


@dataclass
class AuditEntry:
    event_id: str
    actor: str
    action: str
    resource: str
    reason: str
    timestamp: str
    previous_hash: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class GovernanceStore:
    engine: RiskEngine = field(default_factory=RiskEngine)
    repository: DatasetRepository = field(default_factory=DatasetRepository)
    news: NewsService = field(default_factory=NewsService)
    audit_log: list[AuditEntry] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    sar_signoffs: list[dict[str, Any]] = field(default_factory=list)
    _case_cache: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.audit_log:
            self.record_audit("SYSTEM", "DATASET_LOADED", "LOCAL_DATASET", "Local KYC and transaction datasets loaded into risk intelligence engine")

    def summary(self) -> dict[str, Any]:
        if not self._case_cache:
            self._case_cache = self.repository.top_cases(self.engine, limit=30)
        dataset = self.repository.summary()
        critical = sum(1 for item in self._case_cache if item["assessment"]["risk_level"] == "CRITICAL")
        high = sum(1 for item in self._case_cache if item["assessment"]["risk_level"] == "HIGH")
        return {
            "accounts_monitored": dataset["clients_loaded"],
            "transactions_loaded": dataset["transactions_loaded"],
            "saml_dataset_rows": dataset["saml_dataset_rows"],
            "critical_risk": critical,
            "high_risk": high,
            "pending_reviews": max(0, critical + high - len(self.reviews)),
            "awaiting_signoff": sum(1 for item in self._case_cache if item["assessment"].get("sar_recommended")),
            "false_positives_prevented": dataset["false_positives_prevented"],
            "audit_events": len(self.audit_log),
            "data_source": "Local KYC and transaction dataset",
        }

    def cases(self, role: str = "compliance") -> list[dict[str, Any]]:
        if not self._case_cache:
            self._case_cache = self.repository.top_cases(self.engine, limit=30)
        return [self._case_row(item["client"], item["assessment"]) for item in self._case_cache]

    def case_detail(self, customer_id: str, role: str = "compliance") -> dict[str, Any]:
        client = self.repository.get_client(customer_id)
        if not client and self._case_cache:
            client = self._case_cache[0]["client"]
        if not client:
            raise KeyError("No local client dataset found")

        payload = self.repository.payload_for_client(client["client_id"])
        assessment = self.engine.assess(payload).to_dict()
        transactions = self.repository.transaction_detail(client["client_id"])
        status = self._status(client["client_id"])
        sensitive_visible = role in {"compliance", "investigator", "admin"}
        ownership_opacity = float_or_zero(client.get("ownership_opacity_score"))

        return {
            "case_id": f"CASE-{int(client['client_id']):04d}",
            "customer_id": client["client_id"],
            "name": client.get("client_name") or f"Customer {client['client_id']}",
            "status": status,
            "assigned_team": self._assigned_team(assessment),
            "role": role,
            "sensitive_visible": sensitive_visible,
            "profile": {
                "client_type": client.get("client_type"),
                "country": client.get("country"),
                "sector": client.get("sector"),
                "sector_risk": client.get("sector_risk"),
                "pep_flag": bool(flag(client, "pep_flag")),
                "sanctions_flag": bool(flag(client, "sanctions_flag")),
                "ownership_opacity_score": ownership_opacity,
                "beneficial_owner": "Restricted - available to authorized reviewers" if not sensitive_visible else f"Linked party for {client.get('client_name')}",
            },
            "assessment": assessment,
            "transactions": transactions,
            "timeline": self._timeline(assessment, transactions),
            "evidence": self._evidence(client, assessment, transactions),
            "sar_draft": self._sar_draft(client, assessment),
            "reviews": [item for item in self.reviews if item["customer_id"] == client["client_id"]],
            "sar_signoffs": [item for item in self.sar_signoffs if item["customer_id"] == client["client_id"]],
        }

    def live_news(self, customer_id: str) -> dict[str, Any]:
        client = self.repository.get_client(customer_id)
        if not client:
            raise KeyError("Unknown customer")
        result = self.news.search_company_risk(client.get("client_name") or customer_id)
        self.record_audit("AI_AGENT", "LIVE_NEWS_LOOKUP", customer_id, result.get("message", "Live news lookup requested"))
        return result

    def submit_review(self, customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        actor = str(payload.get("actor") or "Compliance Officer").strip()
        if not action or not reason:
            raise ValueError("Review action and reason are required")

        review = {
            "review_id": f"REV-{len(self.reviews) + 1:04d}",
            "customer_id": customer_id,
            "action": action,
            "reason": reason,
            "actor": actor,
            "timestamp": _now(),
        }
        self.reviews.append(review)
        self.record_audit(actor, "HUMAN_REVIEW_SUBMITTED", customer_id, f"{action}: {reason}")
        return review

    def signoff_sar(self, customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        reason = str(payload.get("reason") or "").strip()
        actor = str(payload.get("actor") or "Compliance Officer").strip()
        if not reason:
            raise ValueError("SAR sign-off reason is required")

        signoff = {
            "signoff_id": f"SAR-SIGN-{len(self.sar_signoffs) + 1:04d}",
            "customer_id": customer_id,
            "actor": actor,
            "reason": reason,
            "status": "SIGNED_FOR_HUMAN_REVIEW",
            "timestamp": _now(),
        }
        self.sar_signoffs.append(signoff)
        self.record_audit(actor, "SAR_DRAFT_SIGNED_OFF", customer_id, reason)
        return signoff

    def audit(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in reversed(self.audit_log)]

    def record_audit(self, actor: str, action: str, resource: str, reason: str) -> AuditEntry:
        previous_hash = self.audit_log[-1].hash if self.audit_log else "GENESIS"
        timestamp = _now()
        event_id = f"AUD-{len(self.audit_log) + 1:05d}"
        digest = sha256(f"{event_id}|{actor}|{action}|{resource}|{reason}|{timestamp}|{previous_hash}".encode("utf-8")).hexdigest()
        entry = AuditEntry(event_id, actor, action, resource, reason, timestamp, previous_hash, digest)
        self.audit_log.append(entry)
        return entry

    @staticmethod
    def _case_row(client: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": f"CASE-{int(client['client_id']):04d}",
            "customer_id": client["client_id"],
            "name": client.get("client_name"),
            "status": "Requires Review" if assessment.get("trigger_investigation") else "Monitoring",
            "risk_score": assessment["risk_score"],
            "risk_level": assessment["risk_level"],
            "confidence_score": assessment["confidence_score"],
            "assigned_team": "Enhanced Due Diligence" if assessment["risk_score"] >= 81 else "Risk Monitoring",
            "summary": assessment["top_reasons"][0] if assessment.get("top_reasons") else "Routine monitoring profile",
        }

    @staticmethod
    def _assigned_team(assessment: dict[str, Any]) -> str:
        if assessment["risk_score"] >= 81:
            return "Enhanced Due Diligence"
        if assessment["risk_score"] >= 61:
            return "Risk Monitoring"
        return "Periodic Review"

    def _status(self, customer_id: str) -> str:
        signed = [item for item in self.sar_signoffs if item["customer_id"] == customer_id]
        reviewed = [item for item in self.reviews if item["customer_id"] == customer_id]
        if signed:
            return "SAR Draft Signed Off"
        if reviewed:
            return reviewed[-1]["action"]
        return "Requires Review"

    @staticmethod
    def _timeline(assessment: dict[str, Any], transactions: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"date": "T-21 days", "score": max(0, assessment["risk_score"] - assessment["risk_delta"]), "event": "Prior monitoring baseline from stored score history"},
            {"date": "T-7 days", "score": assessment["base_score"], "event": f"Transaction aggregation reviewed across {transactions['count']} local transaction(s)"},
            {"date": "Today", "score": assessment["risk_score"], "event": assessment["timeline_event"]["reason"]},
        ]

    @staticmethod
    def _evidence(client: dict[str, Any], assessment: dict[str, Any], transactions: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = [
            {"id": f"KYC-{client['client_id']}", "source": "KYC profile dataset", "confidence": 0.88, "claim": f"Sector risk: {client.get('sector_risk')} | Country: {client.get('country')}"},
            {"id": f"TXN-{client['client_id']}", "source": "Transaction dataset", "confidence": 0.80, "claim": f"{transactions['typology_hits']} typology hit(s), {transactions['high_risk_country_transfers']} high-risk jurisdiction transfer(s)"},
        ]
        if flag(client, "sanctions_flag") or flag(client, "ofac_country_flag"):
            evidence.append({"id": f"SAN-{client['client_id']}", "source": "Sanctions flags dataset", "confidence": 0.92, "claim": "Sanctions or OFAC exposure flag present"})
        if flag(client, "sectoral_sanctions_flag"):
            evidence.append({"id": f"MEDIA-{client['client_id']}", "source": "Sectoral sanctions signal", "confidence": 0.72, "claim": "Sectoral sanctions exposure requires adverse-media review"})
        return evidence

    @staticmethod
    def _sar_draft(client: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject": f"Corporate Entity {client['client_id']}, {client.get('client_name')}",
            "activity": "; ".join(assessment.get("top_reasons", [])[:3]) or "No material suspicious activity identified.",
            "recommendation": "Draft SAR recommended for human review only; no automatic filing." if assessment.get("sar_recommended") else "Monitor and continue evidence collection.",
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()