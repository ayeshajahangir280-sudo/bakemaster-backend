from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.inventory.models import StockAdjustment, StockTransaction, WastageDocument
from apps.inventory.posting import post_movement
from apps.inventory.services import get_available_stock
from apps.locations.models import Location
from apps.master_data.models import ItemCategory, RawMaterial, UnitOfMeasurement


class StockDocumentWorkflowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user("docs@test.local","password",full_name="Admin",employee_code="DOCS",role="ADMINISTRATOR")
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.unit=UnitOfMeasurement.objects.create(code="KG-D",name="Kilogram")
        category=ItemCategory.objects.create(name="Raw-D",kind="RM")
        self.item=RawMaterial.objects.create(material_code="RM-D",name="Flour",category=category,base_unit=self.unit,purchase_unit=self.unit,consumption_unit=self.unit)
        self.location=Location.objects.create(code="WH-D",name="Warehouse",location_type="RAW_MATERIAL_WAREHOUSE")
        post_movement(item=self.item,location=self.location,quantity=Decimal("10"),direction="IN",transaction_number="DOC-OPEN",transaction_type="OPENING_STOCK",reference_type="OpeningStock",reference_id=self.item.id,unit=self.unit,user=self.user,incoming_unit_cost=Decimal("2"))

    def payload(self, **extra):
        data={"raw_material":str(self.item.id),"location":str(self.location.id),"quantity":"3","unit":str(self.unit.id),"reason":"Damaged packaging","notes":"Counted by supervisor"}
        data.update(extra);return data

    def action(self,base,pk,name,data=None):return self.client.post(f"/api/inventory/{base}/{pk}/{name}/",data or {},format="json")

    def test_wastage_has_no_effect_until_post_and_cancel_is_exact_and_idempotent(self):
        response=self.client.post("/api/inventory/wastage/",self.payload(wastage_date=str(timezone.localdate())),format="json")
        self.assertEqual(response.status_code,201);pk=response.data["id"]
        self.assertEqual(get_available_stock(self.item,self.location),Decimal("10"))
        for name in ("submit","approve","post"):self.assertEqual(self.action("wastage",pk,name).status_code,200)
        self.assertEqual(get_available_stock(self.item,self.location),Decimal("7"))
        self.assertEqual(StockTransaction.objects.filter(reference_type="WastageDocument").count(),1)
        self.assertEqual(self.action("wastage",pk,"post").status_code,200)
        self.assertEqual(StockTransaction.objects.filter(reference_type="WastageDocument").count(),1)
        self.assertEqual(self.action("wastage",pk,"cancel",{"reason":"Entered twice"}).status_code,200)
        self.assertEqual(get_available_stock(self.item,self.location),Decimal("10"))
        self.assertEqual(self.action("wastage",pk,"cancel",{"reason":"Repeated"}).status_code,200)
        self.assertEqual(StockTransaction.objects.filter(reference_type="WastageDocument").count(),2)
        self.assertEqual(WastageDocument.objects.get(pk=pk).status,"CANCELLED")

    def test_negative_adjustment_rejects_insufficient_stock_atomically(self):
        response=self.client.post("/api/inventory/adjustments/",self.payload(adjustment_date=str(timezone.localdate()),direction="NEGATIVE"),format="json")
        self.assertEqual(response.status_code,201);pk=response.data["id"]
        StockAdjustment.objects.filter(pk=pk).update(quantity=Decimal("11"))
        for name in ("submit","approve"):self.assertEqual(self.action("adjustments",pk,name).status_code,200)
        response=self.action("adjustments",pk,"post")
        self.assertEqual(response.status_code,400)
        self.assertEqual(get_available_stock(self.item,self.location),Decimal("10"))
        self.assertEqual(StockAdjustment.objects.get(pk=pk).status,"APPROVED")
