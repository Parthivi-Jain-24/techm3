import unittest

from fastapi.testclient import TestClient

from risk_engine.api import app


class GovernanceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        cases = self.client.get("/governance/cases?role=compliance").json()
        self.customer_id = cases[0]["customer_id"]

    def test_governance_case_contains_assessment(self) -> None:
        response = self.client.get(f"/governance/cases/{self.customer_id}?role=compliance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer_id"], self.customer_id)
        self.assertIn("assessment", data)
        self.assertIn("component_details", data["assessment"])
        self.assertIn("transactions", data)
        self.assertNotEqual(data["profile"]["beneficial_owner"], "Restricted - available to authorized reviewers")

    def test_rbac_masks_sensitive_fields_for_auditor(self) -> None:
        response = self.client.get(f"/governance/cases/{self.customer_id}?role=auditor")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["profile"]["beneficial_owner"], "Restricted - available to authorized reviewers")

    def test_review_requires_reason(self) -> None:
        response = self.client.post(f"/governance/cases/{self.customer_id}/review", json={"action": "Approve Escalation"})
        self.assertEqual(response.status_code, 400)

    def test_review_action_updates_audit(self) -> None:
        response = self.client.post(
            f"/governance/cases/{self.customer_id}/review",
            json={"action": "Approve Escalation", "reason": "Evidence is sufficient", "actor": "Compliance Officer"},
        )
        self.assertEqual(response.status_code, 200)
        audit_response = self.client.get("/governance/audit")
        self.assertEqual(audit_response.status_code, 200)
        self.assertTrue(any(item["action"] == "HUMAN_REVIEW_SUBMITTED" for item in audit_response.json()))

    def test_live_news_endpoint_is_safe_without_key(self) -> None:
        response = self.client.get(f"/governance/cases/{self.customer_id}/live-news")
        self.assertEqual(response.status_code, 200)
        self.assertIn("enabled", response.json())


if __name__ == "__main__":
    unittest.main()