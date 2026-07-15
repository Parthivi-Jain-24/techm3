import unittest

from risk_engine import RiskEngine


class RiskEngineTests(unittest.TestCase):
    def test_clean_customer_is_low_risk(self) -> None:
        assessment = RiskEngine().assess({
            "customer_id": "CLEAN-1",
            "previous_score": 10,
            "kyc": {"existing_kyc_risk": "LOW", "sector": "software", "country": "India"},
        })

        self.assertLessEqual(assessment.risk_score, 30)
        self.assertEqual(assessment.risk_level.value, "LOW")
        self.assertFalse(assessment.trigger_investigation)
        self.assertFalse(assessment.sar_recommended)

    def test_hidden_sanctioned_ubo_gets_escalation_floor(self) -> None:
        assessment = RiskEngine().assess({
            "customer_id": "CUST-2041",
            "previous_score": 52,
            "kyc": {"existing_kyc_risk": "MEDIUM", "sector": "Crypto"},
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
                "confidence": 0.82,
                "evidence_id": "EVD-407",
            },
            "ownership": {
                "sanctioned_ubo": True,
                "shell_layers": 3,
                "confidence": 0.91,
                "evidence_id": "EVD-501",
            },
            "fatf_high_risk": True,
        })

        self.assertEqual(assessment.risk_level.value, "CRITICAL")
        self.assertEqual(assessment.escalation_floor, 85)
        self.assertLess(assessment.base_score, assessment.risk_score)
        self.assertTrue(assessment.trigger_investigation)
        self.assertTrue(assessment.sar_recommended)
        self.assertIn("EVD-203", assessment.evidence_ids)
        self.assertIn("sub_factors", assessment.component_details[1].to_dict())

    def test_possible_name_match_does_not_auto_recommend_sar(self) -> None:
        assessment = RiskEngine().assess({
            "customer_id": "FP-1",
            "previous_score": 20,
            "sanctions": {
                "has_match": True,
                "match_confidence": 0.42,
                "relationship": "unrelated person",
                "source": "OpenSanctions",
                "evidence_id": "EVD-900",
            },
        })

        self.assertLess(assessment.risk_score, 61)
        self.assertIsNone(assessment.escalation_floor)
        self.assertFalse(assessment.trigger_investigation)
        self.assertFalse(assessment.sar_recommended)

    def test_velocity_is_reported_separately(self) -> None:
        assessment = RiskEngine().assess({
            "customer_id": "TREND-1",
            "previous_score": 50,
            "score_n_days_ago": 30,
            "n_days": 20,
            "kyc": {"existing_kyc_risk": "HIGH", "confidence": 1.0},
            "transactions": {"suspicious_probability": 0.9},
            "adverse_media": {"negative_news_found": True, "severity": "HIGH", "confidence": 0.9},
        })

        self.assertIsNotNone(assessment.velocity["points_per_day"])
        self.assertGreater(assessment.velocity["points_per_day"], 0)
        self.assertNotIn("velocity", assessment.breakdown)


if __name__ == "__main__":
    unittest.main()