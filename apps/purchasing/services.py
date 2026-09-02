from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.inventory.models import StockTransaction
from .models import PurchaseInvoice,SupplierLedger
from apps.inventory.posting import post_movement
@transaction.atomic
def post_purchase(pk,user):
 inv=PurchaseInvoice.objects.select_for_update().prefetch_related("items").get(pk=pk)
 if inv.status not in ("DRAFT","APPROVED"): raise ValidationError("Only draft or approved purchases can be posted.")
 items=list(inv.items.all())
 if not items: raise ValidationError("At least one purchase item is required.")
 sub=discount=vat=Decimal("0")
 for i in items:
  if i.quantity<=0 or i.purchase_rate<0: raise ValidationError("Quantities must be positive and rates non-negative.")
  base=i.quantity*i.purchase_rate; i.tax_amount=(base-i.discount_amount)*i.tax_rate/Decimal("100"); i.line_total=base-i.discount_amount+i.tax_amount; i.save(update_fields=["tax_amount","line_total"]); sub+=base; discount+=i.discount_amount;vat+=i.tax_amount
  net_value=base-i.discount_amount
  post_movement(item=i.raw_material,location=inv.warehouse,quantity=i.quantity,direction="IN",transaction_number=f"{inv.invoice_number}-{i.id}",transaction_type="PURCHASE",reference_type="PurchaseInvoice",reference_id=inv.id,unit=i.unit,user=user,incoming_unit_cost=net_value/i.quantity,audit_module="purchasing")
 total=sub-discount+vat; inv.subtotal=sub;inv.discount_total=discount;inv.vat_total=vat;inv.grand_total=total;inv.outstanding_amount=total;inv.status="POSTED";inv.posted_at=timezone.now();inv.posted_by=user;inv.save()
 SupplierLedger.objects.create(supplier=inv.supplier,transaction_date=inv.invoice_date,reference_type="PURCHASE",reference_id=inv.id,debit=total)
 return inv
@transaction.atomic
def cancel_purchase(pk,user,reason):
 if not reason: raise ValidationError("Cancellation reason is required.")
 inv=PurchaseInvoice.objects.select_for_update().get(pk=pk)
 if inv.status=="CANCELLED": return inv
 if inv.status not in ("POSTED","PARTIALLY_PAID","OVERDUE"): raise ValidationError("Purchase cannot be cancelled.")
 originals=StockTransaction.objects.select_for_update().filter(reference_type="PurchaseInvoice",reference_id=inv.id,is_reversal=False)
 for o in originals:
  if hasattr(o,"reversal"): raise ValidationError("Purchase was already reversed.")
  post_movement(item=o.raw_material,location=o.destination_location,quantity=o.quantity_in,direction="OUT",transaction_number=f"REV-{o.transaction_number}",transaction_type="PURCHASE_REVERSAL",reference_type="PurchaseInvoice",reference_id=inv.id,unit=o.unit,user=user,outgoing_unit_cost=o.unit_cost,reversal_of=o,is_reversal=True,audit_action="Reverse",audit_module="purchasing")
 SupplierLedger.objects.create(supplier=inv.supplier,transaction_date=timezone.localdate(),reference_type="PURCHASE_CANCELLATION",reference_id=inv.id,credit=inv.grand_total)
 inv.status="CANCELLED";inv.cancelled_at=timezone.now();inv.cancelled_by=user;inv.cancellation_reason=reason;inv.save();return inv
