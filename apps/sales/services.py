from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inventory.models import StockTransaction
from apps.inventory.services import get_available_stock, get_average_cost
from apps.inventory.posting import post_movement
from .models import CustomerLedger, SalesInvoice,SalesInvoiceItem,SalesReturn,SalesReturnItem
from apps.locations.models import Location


@transaction.atomic
def post_sale(pk, user):
    invoice = SalesInvoice.objects.select_for_update().prefetch_related("items").get(pk=pk)
    if invoice.status not in {"DRAFT", "APPROVED"}:
        raise ValidationError("Only a draft or approved sales invoice can be posted.")
    items = list(invoice.items.select_related("finished_product", "unit"))
    if not items:
        raise ValidationError("At least one sales item is required.")
    subtotal = discount = vat = cogs = Decimal("0")
    costs = []
    for item in items:
        if item.quantity <= 0 or item.selling_price < 0:
            raise ValidationError("Quantities must be positive and prices non-negative.")
        StockTransaction.objects.select_for_update().filter(
            finished_product=item.finished_product,
            destination_location=invoice.sales_location,
        )
        available = get_available_stock(item.finished_product, invoice.sales_location)
        if item.quantity > available:
            raise ValidationError(f"Insufficient {item.finished_product.name}. Available: {available}.")
        gross = item.quantity * item.selling_price
        net = gross - item.discount_amount
        item.tax_amount = net * item.tax_rate / Decimal("100")
        item.line_total = net + item.tax_amount
        item.unit_cost_snapshot = get_average_cost(item.finished_product, invoice.sales_location)
        item.cost_total = item.quantity * item.unit_cost_snapshot
        item.gross_profit = net - item.cost_total
        item.save(update_fields=["tax_amount", "line_total", "unit_cost_snapshot", "cost_total", "gross_profit"])
        subtotal += gross; discount += item.discount_amount; vat += item.tax_amount; cogs += item.cost_total
        costs.append(item)
    revenue = subtotal - discount
    total = revenue + vat
    for item in costs:
        post_movement(item=item.finished_product,location=invoice.sales_location,quantity=item.quantity,direction="OUT",transaction_number=f"{invoice.invoice_number}-{item.id}",transaction_type="SALE",reference_type="SalesInvoice",reference_id=invoice.id,unit=item.unit,user=user,remarks=invoice.notes,audit_module="sales")
    invoice.subtotal=subtotal; invoice.discount_total=discount; invoice.vat_total=vat
    invoice.grand_total=total; invoice.cost_of_goods_sold=cogs
    invoice.gross_profit=revenue-cogs
    invoice.gross_margin_percentage=(invoice.gross_profit/revenue*Decimal("100")) if revenue else Decimal("0")
    invoice.outstanding_amount=total; invoice.status="POSTED"
    invoice.posted_at=timezone.now(); invoice.posted_by=user; invoice.save()
    CustomerLedger.objects.create(
        customer=invoice.customer, transaction_date=invoice.invoice_date,
        reference_type="SALE", reference_id=invoice.id, debit=total,
    )
    return invoice


@transaction.atomic
def cancel_sale(pk, user, reason):
    if not str(reason).strip(): raise ValidationError("Cancellation reason is required.")
    invoice=SalesInvoice.objects.select_for_update().get(pk=pk)
    if invoice.status == "CANCELLED": return invoice
    if invoice.status not in {"POSTED", "PARTIALLY_PAID", "OVERDUE"}:
        raise ValidationError("Sales invoice cannot be cancelled.")
    originals=StockTransaction.objects.select_for_update().filter(reference_type="SalesInvoice",reference_id=invoice.id,is_reversal=False)
    for original in originals:
        if hasattr(original,"reversal"): raise ValidationError("Sales invoice was already reversed.")
        post_movement(item=original.finished_product,location=original.source_location,quantity=original.quantity_out,direction="IN",transaction_number=f"REV-{original.transaction_number}",transaction_type="SALE_REVERSAL",reference_type="SalesInvoice",reference_id=invoice.id,unit=original.unit,user=user,incoming_unit_cost=original.unit_cost,remarks=f"Sales cancellation: {reason}",reversal_of=original,is_reversal=True,audit_action="Reverse",audit_module="sales")
    CustomerLedger.objects.create(customer=invoice.customer,transaction_date=timezone.localdate(),reference_type="SALE_CANCELLATION",reference_id=invoice.id,credit=invoice.grand_total)
    invoice.status="CANCELLED";invoice.cancelled_at=timezone.now();invoice.cancelled_by=user
    invoice.cancellation_reason=reason;invoice.outstanding_amount=0;invoice.save();return invoice

@transaction.atomic
def post_return(pk,user):
 invoice_id=SalesReturn.objects.only("original_sales_invoice_id").get(pk=pk).original_sales_invoice_id
 invoice=SalesInvoice.objects.select_for_update().get(pk=invoice_id)
 ret=SalesReturn.objects.select_for_update().prefetch_related("items__original_sales_invoice_item").get(pk=pk)
 if ret.original_sales_invoice_id!=invoice.id:raise ValidationError("The original sales invoice changed; retry the return.")
 if ret.status not in {"DRAFT","SUBMITTED","APPROVED"}:raise ValidationError("Return has already been posted or cancelled.")
 if invoice.status in {"DRAFT","CANCELLED"}:raise ValidationError("Returns require an active posted sales invoice.")
 credit=Decimal("0")
 for line in ret.items.all():
  original=SalesInvoiceItem.objects.select_for_update().get(pk=line.original_sales_invoice_item_id)
  if original.sales_invoice_id!=invoice.id or original.finished_product_id!=line.finished_product_id:raise ValidationError("Invalid original sales line.")
  returned=SalesReturnItem.objects.filter(original_sales_invoice_item=original,sales_return__status="POSTED").exclude(sales_return=ret).aggregate(total=__import__("django.db.models",fromlist=["Sum"]).Sum("return_quantity"))["total"] or Decimal("0")
  remaining=original.quantity-returned
  if line.return_quantity<=0 or line.return_quantity>remaining:raise ValidationError(f"Return quantity exceeds the remaining returnable quantity ({remaining}).")
  location=ret.return_location if line.condition=="SALEABLE" else Location.objects.get_or_create(code="SYS-DAMAGED",defaults={"name":"Damaged Stock","location_type":"DAMAGED_GOODS","is_inventory_location":True})[0]
  line.previously_returned_quantity=returned;line.sold_quantity=original.quantity;line.unit_price=original.selling_price
  ratio=line.return_quantity/original.quantity;line.credit_amount=(original.line_total*ratio).quantize(Decimal("0.01"));line.save()
  post_movement(item=original.finished_product,location=location,quantity=line.return_quantity,direction="IN",transaction_number=f"{ret.return_number}-{line.id}",transaction_type="SALES_RETURN" if line.condition=="SALEABLE" else "DAMAGE",reference_type="SalesReturn",reference_id=ret.id,unit=original.unit,user=user,incoming_unit_cost=original.unit_cost_snapshot,remarks=ret.reason,audit_action="Post return",audit_module="sales_returns")
  credit+=line.credit_amount
 ret.subtotal=credit;ret.credit_total=credit;ret.status="POSTED";ret.posted_at=timezone.now();ret.posted_by=user;ret.save()
 invoice.outstanding_amount=max(Decimal("0"),invoice.outstanding_amount-credit);invoice.save(update_fields=["outstanding_amount"])
 CustomerLedger.objects.create(customer=ret.customer,transaction_date=ret.return_date,reference_type="SALES_RETURN",reference_id=ret.id,credit=credit)
 return ret

@transaction.atomic
def cancel_return(pk,user,reason):
 if not str(reason).strip():raise ValidationError("Cancellation reason is required.")
 invoice_id=SalesReturn.objects.only("original_sales_invoice_id").get(pk=pk).original_sales_invoice_id
 invoice=SalesInvoice.objects.select_for_update().get(pk=invoice_id)
 ret=SalesReturn.objects.select_for_update().get(pk=pk)
 if ret.original_sales_invoice_id!=invoice.id:raise ValidationError("The original sales invoice changed; retry the cancellation.")
 if ret.status=="CANCELLED":return ret
 if ret.status!="POSTED":raise ValidationError("Only a posted return can be cancelled.")
 originals=StockTransaction.objects.select_for_update().filter(reference_type="SalesReturn",reference_id=ret.id,is_reversal=False).order_by("-created_at")
 for original in originals:
  post_movement(item=original.finished_product,location=original.destination_location,quantity=original.quantity_in,direction="OUT",transaction_number=f"REV-{original.transaction_number}",transaction_type="STOCK_ADJUSTMENT_OUT",reference_type="SalesReturn",reference_id=ret.id,unit=original.unit,user=user,outgoing_unit_cost=original.unit_cost,remarks=f"Return cancellation: {reason}",reversal_of=original,is_reversal=True,audit_action="Cancel return",audit_module="sales_returns")
 CustomerLedger.objects.create(customer=ret.customer,transaction_date=timezone.localdate(),reference_type="SALES_RETURN_CANCELLATION",reference_id=ret.id,debit=ret.credit_total)
 invoice.outstanding_amount+=ret.credit_total;invoice.save(update_fields=["outstanding_amount"])
 ret.status="CANCELLED";ret.cancelled_at=timezone.now();ret.cancelled_by=user;ret.cancellation_reason=reason;ret.save();return ret
