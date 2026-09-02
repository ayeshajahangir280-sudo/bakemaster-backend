from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inventory.models import StockTransaction
from apps.locations.models import Location
from apps.master_data.models import ItemCategory, RawMaterial, UnitOfMeasurement


class OpeningRawMaterialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "inventory@test.local",
            "password123",
            full_name="Inventory User",
            employee_code="INV-TEST",
            role="WAREHOUSE",
            allowed_modules=["inventory"],
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.warehouse = Location.objects.create(
            code="RM-WH",
            name="Raw Material Warehouse",
            location_type="RAW_MATERIAL_WAREHOUSE",
        )
        category = ItemCategory.objects.create(name="Ingredients", kind="RM")
        unit = UnitOfMeasurement.objects.create(code="KG", name="Kilogram")
        self.material = RawMaterial.objects.create(
            material_code="RM-FLOUR",
            name="Flour",
            category=category,
            base_unit=unit,
            purchase_unit=unit,
            consumption_unit=unit,
            current_average_cost=Decimal("4.5000"),
        )

    def test_posts_opening_stock_to_ledger(self):
        response = self.client.post(
            "/api/inventory/stock-transactions/opening-raw-material/",
            {
                "raw_material": str(self.material.id),
                "location": str(self.warehouse.id),
                "quantity": "25.500",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        transaction = StockTransaction.objects.get(reference_type="OpeningStock")
        self.assertEqual(transaction.transaction_type, "OPENING_STOCK")
        self.assertEqual(transaction.quantity_in, Decimal("25.500"))
        self.assertEqual(transaction.total_value, Decimal("114.75"))
        self.assertEqual(transaction.destination_location, self.warehouse)
        self.assertEqual(transaction.raw_material, self.material)

    def test_rejects_non_raw_material_warehouse(self):
        shop = Location.objects.create(code="SHOP", name="Shop", location_type="SHOP")

        response = self.client.post(
            "/api/inventory/stock-transactions/opening-raw-material/",
            {
                "raw_material": str(self.material.id),
                "location": str(shop.id),
                "quantity": "10",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StockTransaction.objects.exists())
