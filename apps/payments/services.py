from decimal import Decimal,ROUND_HALF_UP
from uuid import uuid4
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.audit.models import AuditLog
from apps.sales.models import CustomerLedger,SalesInvoice
from apps.purchasing.models import PurchaseInvoice,SupplierLedger
from .models import CustomerPayment,SupplierPayment

MONEY=Decimal("0.01");TOLERANCE=Decimal("0.01")

def payment_number(prefix):return f"{prefix}-{timezone.localdate().year}-{uuid4().hex[:12].upper()}"
def _invoice_status(invoice):
 outstanding=invoice.outstanding_amount.quantize(MONEY,rounding=ROUND_HALF_UP)
 if outstanding<=TOLERANCE:return "PAID"
 if invoice.paid_amount>TOLERANCE:return "PARTIALLY_PAID"
 if invoice.due_date and invoice.due_date<timezone.localdate():return "OVERDUE"
 return "POSTED"
def _audit(payment,user,action,previous,new):
 AuditLog.objects.create(user=user,action=action,module="payments",record_type=payment.__class__.__name__,record_id=payment.pk,record_number=payment.payment_number,description=f"{action} {payment.payment_number}",previous_values={"status":previous},new_values={"status":new})

@transaction.atomic
def post_payment(payment_class,pk,user):
 payment=payment_class.objects.select_for_update().get(pk=pk)
 if payment.status=="POSTED":return payment
 if payment.status!="DRAFT":raise ValidationError("Only draft payments can be posted.")
 customer=isinstance(payment,CustomerPayment)
 allocations=list(payment.allocations.select_for_update().order_by("id"))
 if not allocations:raise ValidationError("At least one invoice allocation is required before posting.")
 total=sum((x.amount for x in allocations),Decimal("0")).quantize(MONEY)
 if total<=0 or total-payment.amount>TOLERANCE:raise ValidationError("Allocations must be positive and cannot exceed the payment amount.")
 invoice_model=SalesInvoice if customer else PurchaseInvoice
 invoice_ids=[x.invoice_id for x in allocations]
 invoices={x.pk:x for x in invoice_model.objects.select_for_update().filter(pk__in=invoice_ids)}
 for allocation in allocations:
  invoice=invoices.get(allocation.invoice_id)
  if not invoice:raise ValidationError("An allocated invoice no longer exists.")
  party_matches=invoice.customer_id==payment.customer_id if customer else invoice.supplier_id==payment.supplier_id
  if not party_matches:raise ValidationError(f"Invoice {invoice.invoice_number} belongs to another party.")
  if invoice.status in {"DRAFT","CANCELLED"}:raise ValidationError(f"Invoice {invoice.invoice_number} is {invoice.status.lower()} and cannot receive payment.")
  if allocation.amount-invoice.outstanding_amount>TOLERANCE:raise ValidationError(f"Allocation for {invoice.invoice_number} exceeds outstanding amount {invoice.outstanding_amount}.")
 for allocation in allocations:
  invoice=invoices[allocation.invoice_id];invoice.paid_amount=(invoice.paid_amount+allocation.amount).quantize(MONEY);invoice.outstanding_amount=max(Decimal("0"),(invoice.outstanding_amount-allocation.amount).quantize(MONEY));invoice.status=_invoice_status(invoice);invoice.save(update_fields=["paid_amount","outstanding_amount","status"])
 ledger_model=CustomerLedger if customer else SupplierLedger
 ledger_model.objects.create(**({"customer":payment.customer} if customer else {"supplier":payment.supplier}),transaction_date=payment.payment_date,reference_type=payment.__class__.__name__,reference_id=payment.pk,debit=Decimal("0") if customer else total,credit=total if customer else Decimal("0"))
 payment.status="POSTED";payment.posted_by=user;payment.posted_at=timezone.now();payment.save(update_fields=["status","posted_by","posted_at","updated_at"]);_audit(payment,user,"Post","DRAFT","POSTED");return payment

@transaction.atomic
def cancel_payment(payment_class,pk,user,reason):
 payment=payment_class.objects.select_for_update().get(pk=pk)
 if payment.status=="CANCELLED":return payment
 if payment.status=="DRAFT":
  payment.status="CANCELLED";payment.cancelled_by=user;payment.cancelled_at=timezone.now();payment.cancellation_reason=reason;payment.save();_audit(payment,user,"Cancel","DRAFT","CANCELLED");return payment
 if payment.status!="POSTED":raise ValidationError("Only active payments can be cancelled.")
 customer=isinstance(payment,CustomerPayment);allocations=list(payment.allocations.select_for_update().order_by("id"));invoice_model=SalesInvoice if customer else PurchaseInvoice
 invoices={x.pk:x for x in invoice_model.objects.select_for_update().filter(pk__in=[a.invoice_id for a in allocations])}
 total=Decimal("0")
 for allocation in allocations:
  invoice=invoices[allocation.invoice_id];invoice.paid_amount=max(Decimal("0"),(invoice.paid_amount-allocation.amount).quantize(MONEY));invoice.outstanding_amount=(invoice.outstanding_amount+allocation.amount).quantize(MONEY);invoice.status=_invoice_status(invoice);invoice.save(update_fields=["paid_amount","outstanding_amount","status"]);total+=allocation.amount
 ledger_model=CustomerLedger if customer else SupplierLedger
 ledger_model.objects.create(**({"customer":payment.customer} if customer else {"supplier":payment.supplier}),transaction_date=timezone.localdate(),reference_type=f"{payment.__class__.__name__}Reversal",reference_id=payment.pk,debit=total if customer else Decimal("0"),credit=Decimal("0") if customer else total)
 payment.status="CANCELLED";payment.cancelled_by=user;payment.cancelled_at=timezone.now();payment.cancellation_reason=reason;payment.save(update_fields=["status","cancelled_by","cancelled_at","cancellation_reason","updated_at"]);_audit(payment,user,"Cancel","POSTED","CANCELLED");return payment
