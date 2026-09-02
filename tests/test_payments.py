from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.locations.models import Location
from apps.master_data.models import Customer,PaymentMethod,Supplier
from apps.purchasing.models import PurchaseInvoice,SupplierLedger
from apps.sales.models import CustomerLedger,SalesInvoice
from apps.system_state.models import IdempotencyRecord

class PaymentWorkflowTests(TestCase):
 def setUp(self):
  self.user=User.objects.create_user("pay@test.local","password",full_name="Pay",employee_code="PAY",role="ADMINISTRATOR")
  self.client=APIClient();self.client.force_authenticate(self.user)
  self.location=Location.objects.create(code="PAY-SHOP",name="Shop",location_type="SHOP")
  self.customer=Customer.objects.create(customer_code="PAY-C",name="Customer",assigned_location=self.location)
  self.supplier=Supplier.objects.create(supplier_code="PAY-S",name="Supplier")
  self.method=PaymentMethod.objects.create(name="Bank Transfer")
 def sales_invoice(self,number,amount):return SalesInvoice.objects.create(invoice_number=number,customer=self.customer,invoice_date=timezone.localdate(),sales_location=self.location,status="POSTED",grand_total=amount,outstanding_amount=amount)
 def purchase_invoice(self,number,amount):return PurchaseInvoice.objects.create(invoice_number=number,supplier=self.supplier,invoice_date=timezone.localdate(),warehouse=self.location,status="POSTED",grand_total=amount,outstanding_amount=amount)
 def test_customer_payment_allocates_multiple_invoices_and_cancel_reverses(self):
  first=self.sales_invoice("PAY-SI-1",Decimal("100"));second=self.sales_invoice("PAY-SI-2",Decimal("50"))
  response=self.client.post("/api/customer-payments/",{"customer":str(self.customer.id),"payment_date":str(timezone.localdate()),"amount":"120","payment_method":str(self.method.id),"allocations":[{"invoice":str(first.id),"amount":"100"},{"invoice":str(second.id),"amount":"20"}]},format="json")
  self.assertEqual(response.status_code,201);pk=response.data["id"]
  self.assertEqual(self.client.post(f"/api/customer-payments/{pk}/post/").status_code,200)
  first.refresh_from_db();second.refresh_from_db();self.assertEqual(first.status,"PAID");self.assertEqual(second.status,"PARTIALLY_PAID");self.assertEqual(second.outstanding_amount,Decimal("30"));self.assertEqual(CustomerLedger.objects.count(),1)
  self.assertEqual(self.client.post(f"/api/customer-payments/{pk}/post/").status_code,200);self.assertEqual(CustomerLedger.objects.count(),1)
  self.assertEqual(self.client.post(f"/api/customer-payments/{pk}/cancel/",{"reason":"Bank reversal"},format="json").status_code,200)
  first.refresh_from_db();second.refresh_from_db();self.assertEqual(first.outstanding_amount,Decimal("100"));self.assertEqual(second.outstanding_amount,Decimal("50"));self.assertEqual(CustomerLedger.objects.count(),2)
  self.client.post(f"/api/customer-payments/{pk}/cancel/",{"reason":"retry"},format="json");self.assertEqual(CustomerLedger.objects.count(),2)
 def test_allocation_cannot_exceed_invoice_and_rolls_back(self):
  invoice=self.sales_invoice("PAY-SI-3",Decimal("10"))
  response=self.client.post("/api/customer-payments/",{"customer":str(self.customer.id),"payment_date":str(timezone.localdate()),"amount":"20","payment_method":str(self.method.id),"allocations":[{"invoice":str(invoice.id),"amount":"20"}]},format="json");pk=response.data["id"]
  self.assertEqual(self.client.post(f"/api/customer-payments/{pk}/post/").status_code,400);invoice.refresh_from_db();self.assertEqual(invoice.outstanding_amount,Decimal("10"));self.assertFalse(CustomerLedger.objects.exists())
 def test_supplier_payment_posts_and_cancels(self):
  invoice=self.purchase_invoice("PAY-PI-1",Decimal("75"))
  response=self.client.post("/api/supplier-payments/",{"supplier":str(self.supplier.id),"payment_date":str(timezone.localdate()),"amount":"50","payment_method":str(self.method.id),"allocations":[{"invoice":str(invoice.id),"amount":"50"}]},format="json");pk=response.data["id"]
  self.assertEqual(self.client.post(f"/api/supplier-payments/{pk}/post/").status_code,200);invoice.refresh_from_db();self.assertEqual(invoice.outstanding_amount,Decimal("25"));self.assertEqual(SupplierLedger.objects.get().debit,Decimal("50"))
  self.assertEqual(self.client.post(f"/api/supplier-payments/{pk}/cancel/",{"reason":"Void"},format="json").status_code,200);invoice.refresh_from_db();self.assertEqual(invoice.outstanding_amount,Decimal("75"))
 def test_idempotency_key_replays_and_rejects_payload_change(self):
  invoice=self.sales_invoice("PAY-IDEM",Decimal("50"))
  created=self.client.post("/api/customer-payments/",{"customer":str(self.customer.id),"payment_date":str(timezone.localdate()),"amount":"50","payment_method":str(self.method.id),"allocations":[{"invoice":str(invoice.id),"amount":"50"}]},format="json")
  url=f"/api/customer-payments/{created.data['id']}/post/"
  first=self.client.post(url,{},format="json",HTTP_IDEMPOTENCY_KEY="payment-post-1")
  replay=self.client.post(url,{},format="json",HTTP_IDEMPOTENCY_KEY="payment-post-1")
  conflict=self.client.post(url,{"changed":True},format="json",HTTP_IDEMPOTENCY_KEY="payment-post-1")
  self.assertEqual(first.status_code,200);self.assertEqual(replay.status_code,200)
  self.assertEqual(replay["Idempotency-Replayed"],"true");self.assertEqual(conflict.status_code,409)
  self.assertEqual(CustomerLedger.objects.count(),1);self.assertEqual(IdempotencyRecord.objects.count(),1)
