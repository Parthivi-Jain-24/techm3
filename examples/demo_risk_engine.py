import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_engine import RiskEngine


def main() -> None:
    payload = {
        "customer_id": "CUST-2041",
        "previous_score": 52,
        "kyc": {
            "sector": "Crypto",
            "country": "UAE",
            "existing_kyc_risk": "MEDIUM",
            "pep_flag": False,
            "evidence_id": "EVD-101",
        },
        "sanctions": {
            "has_match": True,
            "match_confidence": 0.94,
            "relationship": "UBO",
            "source": "OFAC SDN",
            "evidence_id": "EVD-203",
        },
        "transactions": {
            "suspicious_probability": 0.76,
            "monthly_volume_change": 2.8,
            "high_risk_country_transfers": 12,
            "typology_hits": 2,
            "evidence_id": "EVD-311",
        },
        "adverse_media": {
            "negative_news_found": True,
            "severity": "HIGH",
            "source": "Reuters",
            "source_count": 2,
            "days_since_event": 3,
            "confidence": 0.82,
            "evidence_id": "EVD-407",
        },
        "ownership": {
            "sanctioned_ubo": True,
            "shell_layers": 3,
            "tax_haven_link": True,
            "confidence": 0.91,
            "evidence_id": "EVD-501",
        },
        "fatf_high_risk": True,
    }

    assessment = RiskEngine().assess(payload)
    print(json.dumps(assessment.to_dict(), indent=2))


if __name__ == "__main__":
    main()

