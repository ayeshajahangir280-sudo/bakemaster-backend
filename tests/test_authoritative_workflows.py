from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.inventory.models import StockTransaction
from apps.inventory.services import get_available_stock, get_average_cost
from apps.locations.models import Location
from apps.master_data.models import Customer, FinishedProduct, ItemCategory, RawMaterial, UnitOfMeasurement
from apps.production.models import ProductionBatch
from apps.production.services import complete_production
from apps.recipes.models import Recipe, RecipeItem
from apps.sales.models import SalesInvoice, SalesInvoiceItem
from apps.sales.services import cancel_sale, post_sale


class AuthoritativeWorkflowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user("flow@test.local","password123",full_name="Flow",employee_code="FLOW",role="ADMINISTRATOR")
        self.unit=UnitOfMeasurement.objects.create(code="KG",name="Kilogram")
        rm_cat=ItemCategory.objects.create(name="RM",kind="RM");fg_cat=ItemCategory.objects.create(name="FG",kind="FG")
        self.material=RawMaterial.objects.create(material_code="RM-1",name="Flour",category=rm_cat,base_unit=self.unit,purchase_unit=self.unit,consumption_unit=self.unit)
        self.product=FinishedProduct.objects.create(product_code="FG-1",name="Bread",category=fg_cat,sales_unit=self.unit)
        self.production_location=Location.objects.create(code="PROD",name="Production",location_type="PRODUCTION")
        self.shop=Location.objects.create(code="SHOP",name="Shop",location_type="SHOP")
        self.recipe=Recipe.objects.create(recipe_number="REC-1",finished_product=self.product,standard_output_quantity=Decimal("10"),output_unit=self.unit,version="1",effective_date=timezone.localdate(),status="ACTIVE",is_default=True)
        RecipeItem.objects.create(recipe=self.recipe,raw_material=self.material,required_quantity=Decimal("5"),unit=self.unit,wastage_percentage=Decimal("10"),unit_cost_snapshot=Decimal("2"))
        StockTransaction.objects.create(transaction_number="OPEN-RM",transaction_date=timezone.now(),transaction_type="OPENING_STOCK",reference_type="OpeningStock",reference_id=self.material.id,raw_material=self.material,destination_location=self.production_location,quantity_in=Decimal("20"),unit=self.unit,unit_cost=Decimal("2"),total_value=Decimal("40"),created_by=self.user)

    def test_production_combines_output_and_consumes_scaled_recipe_with_wastage(self):
        first=ProductionBatch.objects.create(production_number="PRD-1",finished_product=self.product,recipe=self.recipe,planned_quantity=Decimal("10"),production_location=self.production_location,finished_goods_destination=self.shop,batch_number="OLD-A",manufacturing_date=timezone.localdate())
        second=ProductionBatch.objects.create(production_number="PRD-2",finished_product=self.product,recipe=self.recipe,planned_quantity=Decimal("10"),production_location=self.production_location,finished_goods_destination=self.shop,batch_number="OLD-B",manufacturing_date=timezone.localdate())
        complete_production(first.id,self.user);complete_production(second.id,self.user)
        self.assertEqual(get_available_stock(self.material,self.production_location),Decimal("9.0"))
        self.assertEqual(get_available_stock(self.product,self.shop),Decimal("20"))
        self.assertEqual(StockTransaction.objects.filter(transaction_type="PRODUCTION_OUTPUT").count(),2)

    def test_sale_uses_combined_average_cost_and_cancellation_restores_stock(self):
        for number,quantity,cost in [("FG-A","10","2"),("FG-B","10","4")]:
            StockTransaction.objects.create(transaction_number=number,transaction_date=timezone.now(),transaction_type="PRODUCTION_OUTPUT",reference_type="ProductionBatch",reference_id=self.product.id,finished_product=self.product,destination_location=self.shop,quantity_in=Decimal(quantity),unit=self.unit,unit_cost=Decimal(cost),total_value=Decimal(quantity)*Decimal(cost),created_by=self.user)
        customer=Customer.objects.create(customer_code="C-1",name="Customer")
        invoice=SalesInvoice.objects.create(invoice_number="SI-1",customer=customer,invoice_date=timezone.localdate(),sales_location=self.shop)
        item=SalesInvoiceItem.objects.create(sales_invoice=invoice,finished_product=self.product,quantity=Decimal("5"),unit=self.unit,selling_price=Decimal("10"))
        post_sale(invoice.id,self.user);item.refresh_from_db()
        self.assertEqual(item.unit_cost_snapshot,Decimal("3"))
        self.assertEqual(get_available_stock(self.product,self.shop),Decimal("15"))
        cancel_sale(invoice.id,self.user,"Customer request")
        self.assertEqual(get_available_stock(self.product,self.shop),Decimal("20"))
