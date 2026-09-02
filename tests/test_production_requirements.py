from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inventory.models import InventoryBalance
from apps.locations.models import Location
from apps.master_data.models import FinishedProduct, ItemCategory, RawMaterial, UnitOfMeasurement
from apps.recipes.models import Recipe, RecipeItem


class ProductionRequirementsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "production@test.local", "password123", full_name="Production", employee_code="PROD-TEST",
            role="PRODUCTION", allowed_modules=["production"],
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.unit = UnitOfMeasurement.objects.create(code="KG", name="Kilogram")
        self.rm_category = ItemCategory.objects.create(name="Ingredients", kind="RM")
        self.fg_category = ItemCategory.objects.create(name="Cookies", kind="FG")
        self.material = RawMaterial.objects.create(
            material_code="RM-FLOUR", name="Flour", category=self.rm_category,
            base_unit=self.unit, purchase_unit=self.unit, consumption_unit=self.unit,
        )
        self.product = FinishedProduct.objects.create(
            product_code="FG-COOKIE", name="Chocolate Cookie", category=self.fg_category, sales_unit=self.unit,
        )
        self.location = Location.objects.create(code="PROD", name="Production", location_type="PRODUCTION")
        self.recipe = Recipe.objects.create(
            recipe_number="REC-COOKIE", finished_product=self.product, standard_output_quantity=100,
            output_unit=self.unit, version="1", effective_date="2026-09-03", status="ACTIVE", is_default=True,
        )
        RecipeItem.objects.create(recipe=self.recipe, raw_material=self.material, required_quantity=10,
                                  unit=self.unit, wastage_percentage=10)

    def test_calculates_wastage_and_shortage_without_mutating_inventory(self):
        InventoryBalance.objects.create(raw_material=self.material, location=self.location, current_quantity=50)
        before = InventoryBalance.objects.get().current_quantity
        response = self.client.get("/api/production-requirements/", {
            "finished_product": self.product.id, "recipe": self.recipe.id,
            "requested_quantity": "1000", "production_location": self.location.id,
        })
        self.assertEqual(response.status_code, 200)
        item = response.json()["requirements"][0]
        self.assertEqual(item["required_quantity"], "110.000")
        self.assertEqual(item["shortage_quantity"], "60.000")
        self.assertFalse(response.json()["can_produce"])
        self.assertEqual(InventoryBalance.objects.get().current_quantity, before)

    def test_rejects_wrong_recipe_product(self):
        other = FinishedProduct.objects.create(product_code="FG-OTHER", name="Other", category=self.fg_category, sales_unit=self.unit)
        response = self.client.get("/api/production-requirements/", {
            "finished_product": other.id, "recipe": self.recipe.id,
            "requested_quantity": 1, "production_location": self.location.id,
        })
        self.assertEqual(response.status_code, 400)

    def test_requires_production_permission(self):
        self.user.allowed_modules = []
        self.user.save(update_fields=["allowed_modules"])
        response = self.client.get("/api/production-requirements/", {"requested_quantity": 1})
        self.assertEqual(response.status_code, 403)
