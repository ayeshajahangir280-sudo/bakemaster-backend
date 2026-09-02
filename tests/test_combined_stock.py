from decimal import Decimal
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inventory.models import StockTransaction
from apps.inventory.services import get_average_cost, get_finished_product_stock
from apps.inventory.posting import post_movement
from apps.locations.models import Location
from apps.master_data.models import FinishedProduct, ItemCategory, UnitOfMeasurement


class CombinedStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "combined@test.local", "password123", full_name="Inventory User",
            employee_code="COMBINED", role="WAREHOUSE", allowed_modules=["inventory"],
        )
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.unit = UnitOfMeasurement.objects.create(code="PACK", name="Packet")
        category = ItemCategory.objects.create(name="Finished", kind="FG")
        self.product = FinishedProduct.objects.create(
            product_code="FG-COOKIE", name="Butter Cookies", category=category,
            sales_unit=self.unit, standard_cost=Decimal("2.0000"),
        )
        self.dubai = Location.objects.create(
            code="DXB", name="Dubai", location_type="FINISHED_GOODS_WAREHOUSE",
        )
        self.sharjah = Location.objects.create(
            code="SHJ", name="Sharjah", location_type="FINISHED_GOODS_WAREHOUSE",
        )

    def entry(self, number, location, quantity, cost, batch):
        entry,_=post_movement(item=self.product,location=location,quantity=quantity,direction="IN",transaction_number=number,transaction_type="PRODUCTION_OUTPUT",reference_type="ProductionBatch",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=cost)
        StockTransaction.objects.filter(pk=entry.pk).update(batch=batch)
        entry.batch=batch
        return entry

    def test_historical_batches_combine_by_product_and_location(self):
        first = self.entry("OLD-A", self.dubai, Decimal("40"), Decimal("2"), "A")
        second = self.entry("OLD-B", self.dubai, Decimal("60"), Decimal("3"), "B")
        self.assertEqual(get_finished_product_stock(self.product, self.dubai), Decimal("100"))
        self.assertEqual(get_average_cost(self.product, self.dubai), Decimal("2.6"))
        self.assertEqual(StockTransaction.objects.filter(pk__in=[first.pk, second.pk]).count(), 2)

    def test_locations_remain_separate(self):
        self.entry("DXB-IN", self.dubai, Decimal("100"), Decimal("2"), "A")
        self.entry("SHJ-IN", self.sharjah, Decimal("50"), Decimal("2"), "B")
        self.assertEqual(get_finished_product_stock(self.product, self.dubai), Decimal("100"))
        self.assertEqual(get_finished_product_stock(self.product, self.sharjah), Decimal("50"))

    def test_opening_finished_goods_no_longer_requires_batch(self):
        response = self.client.post("/api/inventory/stock-transactions/opening-finished-goods/", {
            "finished_product": str(self.product.id), "location": str(self.dubai.id), "quantity": "25",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockTransaction.objects.get().batch, "")

    def test_negative_adjustment_uses_combined_stock_and_average_cost(self):
        self.entry("IN-A", self.dubai, Decimal("100"), Decimal("2"), "A")
        self.entry("IN-B", self.dubai, Decimal("50"), Decimal("3"), "B")
        response = self.client.post("/api/inventory/stock-transactions/adjust/", {
            "item_type": "FG", "item": str(self.product.id), "location": str(self.dubai.id),
            "quantity": "-20", "reason": "Count correction",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        outgoing = StockTransaction.objects.get(reference_type="StockAdjustment")
        self.assertEqual(outgoing.quantity_out, Decimal("20"))
        self.assertEqual(outgoing.unit_cost.quantize(Decimal("0.0001")), Decimal("2.3333"))
        self.assertEqual(get_finished_product_stock(self.product, self.dubai), Decimal("130"))

    def test_negative_adjustment_cannot_exceed_combined_stock(self):
        self.entry("IN", self.dubai, Decimal("10"), Decimal("2"), "A")
        response = self.client.post("/api/inventory/stock-transactions/adjust/", {
            "item_type": "FG", "item": str(self.product.id), "location": str(self.dubai.id),
            "quantity": "-11", "reason": "Invalid",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockTransaction.objects.count(), 1)

    def test_balances_api_returns_one_row_for_old_batches(self):
        self.entry("OLD-A", self.dubai, Decimal("40"), Decimal("2"), "A")
        self.entry("OLD-B", self.dubai, Decimal("60"), Decimal("3"), "B")
        response = self.client.get("/api/inventory/stock-transactions/balances/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["quantity"], Decimal("100"))
