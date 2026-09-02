from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.inventory.models import StockTransaction
from apps.inventory.posting import post_movement
from apps.locations.models import Location
from apps.master_data.models import FinishedProduct, ItemCategory, RawMaterial, Supplier, UnitOfMeasurement
from apps.production.models import ProductionBatch
from apps.production.services import complete_production
from apps.purchasing.models import PurchaseInvoice, PurchaseInvoiceItem
from apps.purchasing.services import post_purchase
from apps.recipes.models import Recipe, RecipeItem


class Command(BaseCommand):
    help = "Seed idempotent bakery data for the WebMCP challenge demo."

    def handle(self, *args, **options):
        with transaction.atomic():
            admin = User.objects.filter(email="admin@mcp.zekrasweets.com", is_active=True).first() or User.objects.filter(role="ADMINISTRATOR", is_active=True).first()
            if not admin:
                raise RuntimeError("An active administrator is required before seeding demo data.")
            admin.allowed_modules = [module for module, _ in User.MODULES]
            admin.can_access_all_locations = True
            admin.save(update_fields=["allowed_modules", "can_access_all_locations"])

            units = {code: UnitOfMeasurement.objects.get_or_create(code=code, defaults={"name": name})[0] for code, name in {
                "KG": "Kilogram", "L": "Litre", "PCS": "Pieces", "COOKIE": "Cookie",
            }.items()}
            categories = {kind: ItemCategory.objects.get_or_create(name=name, kind=kind)[0] for kind, name in {"RM": "WebMCP Ingredients", "FG": "WebMCP Cookies"}.items()}
            locations = {}
            for code, name, kind in [("RMW", "Main Warehouse", "RAW_MATERIAL_WAREHOUSE"), ("PROD", "Production Department", "PRODUCTION"), ("FGW", "Finished Goods Store", "FINISHED_GOODS_WAREHOUSE"), ("DXB", "Dubai Branch", "SHOP")]:
                locations[code], _ = Location.objects.get_or_create(code=code, defaults={"name": name, "location_type": kind, "is_sales_location": kind == "SHOP", "is_production_location": kind == "PRODUCTION"})

            material_specs = {
                "FLOUR": ("Flour", "KG", 3.5, 100, 80), "SUGAR": ("Sugar", "KG", 4, 50, 40), "BUTTER": ("Butter", "KG", 18, 40, 30),
                "CHOC": ("Chocolate", "KG", 28, 15, 12), "COCOA": ("Cocoa Powder", "KG", 22, 15, 10), "VANILLA": ("Vanilla Essence", "L", 35, 8, 5),
                "BAKING": ("Baking Powder", "KG", 8, 10, 7), "SALT": ("Salt", "KG", 2, 8, 5), "ALMONDS": ("Almonds", "KG", 32, 30, 20), "BOX": ("Packaging Box", "PCS", 1.5, 800, 500),
            }
            materials = {}
            for code, (name, unit, cost, minimum, reorder) in material_specs.items():
                materials[code], _ = RawMaterial.objects.update_or_create(material_code=f"W-{code}", defaults={"name": name, "category": categories["RM"], "base_unit": units[unit], "purchase_unit": units[unit], "consumption_unit": units[unit], "conversion_factor": 1, "current_average_cost": cost, "minimum_stock": minimum, "reorder_level": reorder, "status": "ACTIVE"})

            products = {}
            for code, name, price, cost in [("CHOC", "Chocolate Cookies", 45, 18), ("ALMOND", "Almond Cookies", 55, 22), ("BUTTER", "Butter Cookies", 40, 16)]:
                products[code], _ = FinishedProduct.objects.update_or_create(product_code=f"W-{code}", defaults={"name": name, "category": categories["FG"], "sales_unit": units["COOKIE"], "standard_sales_price": price, "standard_cost": cost, "minimum_stock": 100, "status": "ACTIVE"})

            recipes = {
                "CHOC": [("FLOUR", 5, 2), ("SUGAR", 2, 2), ("BUTTER", 2, 2), ("CHOC", 2, 2), ("COCOA", Decimal(".5"), 2), ("VANILLA", Decimal(".1"), 1), ("BAKING", Decimal(".2"), 2), ("SALT", Decimal(".05"), 1), ("BOX", 10, 1)],
                "ALMOND": [("FLOUR", 5, 2), ("SUGAR", 2, 2), ("BUTTER", 2, 2), ("ALMONDS", 1.5, 2), ("VANILLA", Decimal(".1"), 1), ("BAKING", Decimal(".2"), 2), ("SALT", Decimal(".05"), 1), ("BOX", 10, 1)],
                "BUTTER": [("FLOUR", 5, 2), ("SUGAR", 2, 2), ("BUTTER", 2.5, 2), ("VANILLA", Decimal(".1"), 1), ("BAKING", Decimal(".2"), 2), ("SALT", Decimal(".05"), 1), ("BOX", 10, 1)],
            }
            for code, lines in recipes.items():
                recipe, _ = Recipe.objects.update_or_create(recipe_number=f"W-REC-{code}", defaults={"finished_product": products[code], "standard_output_quantity": 100, "output_unit": units["COOKIE"], "version": "1.0", "effective_date": timezone.localdate(), "status": "ACTIVE", "is_default": True, "notes": "WebMCP challenge demo recipe"})
                RecipeItem.objects.filter(recipe=recipe).delete()
                for material, quantity, wastage in lines:
                    unit_code = "L" if material == "VANILLA" else "PCS" if material == "BOX" else "KG"
                    RecipeItem.objects.create(recipe=recipe, raw_material=materials[material], required_quantity=quantity, unit=units[unit_code], wastage_percentage=wastage, unit_cost_snapshot=materials[material].current_average_cost)

            stock = {"FLOUR": 60, "SUGAR": 30, "BUTTER": 25, "CHOC": 10, "COCOA": 10, "VANILLA": 5, "BAKING": 5, "SALT": 5, "ALMONDS": 20, "BOX": 500}
            for code, quantity in stock.items():
                material = materials[code]
                if not StockTransaction.objects.filter(transaction_number=f"W-OPEN-{code}").exists():
                    post_movement(item=material, location=locations["PROD"], quantity=quantity, direction="IN", transaction_number=f"W-OPEN-{code}", transaction_type="OPENING_STOCK", reference_type="WebMCPDemo", reference_id=material.id, unit=material.consumption_unit, user=admin, incoming_unit_cost=material.current_average_cost, remarks="WebMCP demo production stock")

            suppliers = [("W-EMS", "Emirates Food Supplies"), ("W-GIT", "Gulf Ingredients Trading"), ("W-PBM", "Premium Baking Materials LLC")]
            supplier_rows = [Supplier.objects.update_or_create(supplier_code=code, defaults={"name": name, "phone": "+971 4 555 0100", "email": f"demo@{code.lower()}.example", "payment_terms_days": 30, "status": "ACTIVE"})[0] for code, name in suppliers]

            for index, material_code in enumerate(["FLOUR", "ALMONDS"]):
                invoice, created = PurchaseInvoice.objects.get_or_create(invoice_number=f"W-HIST-PI-{index + 1}", defaults={"supplier": supplier_rows[index], "invoice_date": timezone.localdate(), "warehouse": locations["RMW"], "notes": "WebMCP demo historical purchase"})
                if created:
                    PurchaseInvoiceItem.objects.create(purchase_invoice=invoice, raw_material=materials[material_code], quantity=20, unit=materials[material_code].purchase_unit, purchase_rate=materials[material_code].current_average_cost, tax_rate=0)
                    post_purchase(invoice.id, admin)

            for index, product_code in enumerate(["ALMOND", "BUTTER"]):
                batch, created = ProductionBatch.objects.get_or_create(production_number=f"W-HIST-PRD-{index + 1}", defaults={"finished_product": products[product_code], "recipe": Recipe.objects.get(recipe_number=f"W-REC-{product_code}"), "planned_quantity": 100, "actual_produced_quantity": 100, "production_location": locations["PROD"], "finished_goods_destination": locations["FGW"], "batch_number": f"W-HIST-{index + 1}", "manufacturing_date": timezone.localdate(), "remarks": "WebMCP demo historical production"})
                if created:
                    complete_production(batch.id, admin, 100)

        self.stdout.write(self.style.SUCCESS("WebMCP demo data seeded: 4 locations, 10 materials, 3 products, 3 recipes, 3 suppliers, opening stock, 2 posted purchases, and 2 completed productions."))
