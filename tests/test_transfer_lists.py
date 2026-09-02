from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.locations.models import Location
from apps.transfers.models import FinishedGoodsTransfer, MaterialTransfer


class TransferListTests(TestCase):
    endpoints = ("/api/material-transfers/", "/api/finished-goods-transfers/")

    def setUp(self):
        self.assigned = Location.objects.create(code="TL-A", name="Assigned", location_type="SHOP")
        self.other = Location.objects.create(code="TL-B", name="Other", location_type="SHOP")
        self.third = Location.objects.create(code="TL-C", name="Third", location_type="SHOP")
        self.admin = User.objects.create_user(
            "transfer-admin@test.local", "password", full_name="Admin", employee_code="TL-ADMIN",
            role="ADMINISTRATOR",
        )
        self.restricted = User.objects.create_user(
            "transfer-user@test.local", "password", full_name="Restricted", employee_code="TL-USER",
            role="WAREHOUSE", assigned_location=self.assigned,
            allowed_modules=["material_transfers", "stock_transfers"],
        )
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_transfers(self):
        today = timezone.localdate()
        MaterialTransfer.objects.create(
            transfer_number="MT-ASSIGNED", transfer_date=today,
            source_location=self.assigned, destination_location=self.other,
        )
        MaterialTransfer.objects.create(
            transfer_number="MT-OTHER", transfer_date=today,
            source_location=self.other, destination_location=self.third,
        )
        FinishedGoodsTransfer.objects.create(
            transfer_number="FG-ASSIGNED", transfer_date=today,
            source_location=self.other, destination_location=self.assigned,
        )
        FinishedGoodsTransfer.objects.create(
            transfer_number="FG-OTHER", transfer_date=today,
            source_location=self.other, destination_location=self.third,
        )

    def test_administrator_lists_all_transfers(self):
        self.create_transfers()
        self.authenticate(self.admin)
        for endpoint in self.endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 2)

    def test_location_restricted_user_only_lists_related_transfers(self):
        self.create_transfers()
        self.authenticate(self.restricted)
        for endpoint in self.endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 1)
            result = response.json()["results"][0]
            self.assertIn(str(self.assigned.id), (result["source_location"], result["destination_location"]))

    def test_empty_transfer_tables_return_empty_lists(self):
        self.authenticate(self.admin)
        for endpoint in self.endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 0)
            self.assertEqual(response.json()["results"], [])
