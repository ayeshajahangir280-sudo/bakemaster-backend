import io,json
from decimal import Decimal
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from apps.locations.models import Location
from apps.master_data.models import Customer,PaymentMethod
from apps.payments.models import CustomerPayment,CustomerPaymentAllocation
from apps.sales.models import SalesInvoice

class PaymentPreflightTests(TestCase):
 def setUp(self):
  self.location=Location.objects.create(code="AUD-P",name="Shop",location_type="SHOP")
  self.customer=Customer.objects.create(customer_code="AUD-C",name="Customer")
  self.other=Customer.objects.create(customer_code="AUD-O",name="Other")
  self.method=PaymentMethod.objects.create(name="Audit Bank")
 def invoice(self,customer=None,status="POSTED",outstanding="100"):
  return SalesInvoice.objects.create(invoice_number=f"AUD-I-{SalesInvoice.objects.count()+1}",customer=customer or self.customer,invoice_date=timezone.localdate(),sales_location=self.location,status=status,grand_total=Decimal(outstanding),outstanding_amount=Decimal(outstanding))
 def test_clean_data_returns_success_and_json_summary(self):
  invoice=self.invoice();payment=CustomerPayment.objects.create(payment_number="AUD-P-1",customer=self.customer,payment_date=timezone.localdate(),amount=Decimal("25"),payment_method=self.method)
  CustomerPaymentAllocation.objects.create(payment=payment,invoice=invoice,amount=Decimal("25"))
  output=io.StringIO();call_command("audit_payment_migration_data",format="json",stdout=output)
  report=json.loads(output.getvalue());self.assertEqual(report["blocking"],0);self.assertEqual(report["warnings"],0)
 def test_blocking_relationship_and_amount_issues_return_nonzero(self):
  invoice=self.invoice(customer=self.other,status="DRAFT",outstanding="5")
  payment=CustomerPayment.objects.create(payment_number="AUD-P-2",customer=self.customer,payment_date=timezone.localdate(),amount=Decimal("10"),payment_method=self.method,status="LEGACY")
  CustomerPaymentAllocation.objects.create(payment=payment,invoice=invoice,amount=Decimal("20"))
  output=io.StringIO()
  with self.assertRaises(CommandError):call_command("audit_payment_migration_data",format="json",stdout=output)
  report=json.loads(output.getvalue());codes={item["code"] for item in report["findings"]}
  self.assertTrue({"INVALID_STATUS","PAYMENT_OVERALLOCATED","PARTY_MISMATCH","INVOICE_NOT_PAYABLE","ALLOCATION_EXCEEDS_OUTSTANDING"}.issubset(codes))
