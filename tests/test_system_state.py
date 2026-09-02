from rest_framework.test import APIClient
from django.test import TestCase

from apps.accounts.models import User
from apps.system_state.models import ERPState


class ERPStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "admin@test.local",
            "password123",
            full_name="Admin",
            employee_code="ADMIN-STATE",
            role="ADMINISTRATOR",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_state_round_trip(self):
        self.assertEqual(self.client.get("/api/erp-state/").json(), {"data": None, "revision": 0})
        database = {"uiPreferences": {"dense": True}}
        response = self.client.put("/api/erp-state/", {"data": database, "revision": 0}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/erp-state/").json()["data"], database)

    def test_state_requires_object(self):
        response = self.client.put("/api/erp-state/", {"data": [], "revision": 0}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_stale_state_write_is_rejected(self):
        first=self.client.put("/api/erp-state/",{"data":{"uiPreferences":{}} ,"revision":0},format="json")
        self.assertEqual(first.status_code,200)
        stale=self.client.put("/api/erp-state/",{"data":{"uiPreferences":{"dense":True}},"revision":0},format="json")
        self.assertEqual(stale.status_code,409)
        self.assertEqual(self.client.get("/api/erp-state/").json()["data"],{"uiPreferences":{}})

    def test_transactional_collections_are_rejected(self):
        payload={"purchaseInvoices":[{"id":"fake"}],"stockLedger":[{"quantity":999}],"customerPayments":[{"amount":999}]}
        response=self.client.put("/api/erp-state/",{"data":payload,"revision":0},format="json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(set(response.json()["rejected_keys"]),set(payload))
        self.assertFalse(ERPState.objects.exists())

    def test_nested_disguised_transactional_state_is_rejected(self):
        for preferences in ({"widgets":{"Stock_Ledger":[{"quantity":999}]}},{"PAYMENTS":{"fake":True}},{"layout":[{"purchaseInvoices":[]}]},):
            response=self.client.put("/api/erp-state/",{"data":{"uiPreferences":preferences},"revision":0},format="json")
            self.assertEqual(response.status_code,400)
        self.assertFalse(ERPState.objects.exists())
