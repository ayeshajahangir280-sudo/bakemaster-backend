from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditLog
from .models import InventoryBalance, StockAdjustment, StockTransaction, WastageDocument
from .posting import post_movement


def generated_number(prefix):
    return f"{prefix}-{timezone.localdate().year}-{uuid4().hex[:12].upper()}"


def _audit(document, user, action, previous, new):
    number=getattr(document,"document_number",None) or getattr(document,"adjustment_number","")
    AuditLog.objects.create(user=user,action=action,module="inventory",record_type=document.__class__.__name__,record_id=document.pk,
        record_number=number,description=f"{action} {number}",previous_values={"status":previous},new_values={"status":new})


@transaction.atomic
def transition(document_class, pk, user, target):
    document=document_class.objects.select_for_update().get(pk=pk)
    transitions={"SUBMITTED":("DRAFT",),"APPROVED":("SUBMITTED",)}
    if document.status==target:return document
    if document.status not in transitions[target]:raise ValidationError(f"Only {transitions[target][0].lower()} documents can be {target.lower()}.")
    if target=="APPROVED" and user.role not in {"ADMINISTRATOR","MANAGER"}:raise ValidationError("Manager or administrator approval is required.")
    previous=document.status;document.status=target
    if target=="SUBMITTED":document.submitted_by=user;document.submitted_at=timezone.now()
    else:document.approved_by=user;document.approved_at=timezone.now()
    document.save();_audit(document,user,target.title(),previous,target)
    return document


@transaction.atomic
def post_stock_document(document_class, pk, user):
    document=document_class.objects.select_for_update(of=("self",)).select_related("raw_material","finished_product","location","unit").get(pk=pk)
    if document.status=="POSTED":return document
    if document.status!="APPROVED":raise ValidationError("Only approved documents can be posted.")
    item=document.raw_material or document.finished_product
    is_adjustment=isinstance(document,StockAdjustment)
    direction="IN" if is_adjustment and document.direction=="POSITIVE" else "OUT"
    if direction=="IN" and document.unit_cost is None:raise ValidationError("Incoming unit cost is required for positive adjustments.")
    balance=InventoryBalance.objects.filter(raw_material=document.raw_material,finished_product=document.finished_product,location=document.location).first()
    previous=balance.current_quantity if balance else Decimal("0")
    number=getattr(document,"document_number",None) or document.adjustment_number
    entry,balance=post_movement(item=item,location=document.location,quantity=document.quantity,direction=direction,
        transaction_number=f"{number}-POST",transaction_type="WASTAGE" if not is_adjustment else f"STOCK_ADJUSTMENT_{'IN' if direction=='IN' else 'OUT'}",
        reference_type=document.__class__.__name__,reference_id=document.pk,unit=document.unit,user=user,
        incoming_unit_cost=document.unit_cost if direction=="IN" else None,remarks=document.reason,
        audit_action="Post",outgoing_unit_cost=None)
    document.unit_cost=entry.unit_cost;document.total_value=entry.total_value;document.status="POSTED";document.posted_by=user;document.posted_at=timezone.now()
    if is_adjustment:document.previous_quantity=previous;document.resulting_quantity=balance.current_quantity
    document.save();return document


@transaction.atomic
def cancel_stock_document(document_class, pk, user, reason):
    document=document_class.objects.select_for_update(of=("self",)).select_related("raw_material","finished_product","location","unit").get(pk=pk)
    if document.status=="CANCELLED":return document
    if document.status in {"DRAFT","SUBMITTED","APPROVED"}:
        previous=document.status;document.status="CANCELLED";document.cancelled_by=user;document.cancelled_at=timezone.now();document.cancellation_reason=reason;document.save();_audit(document,user,"Cancel",previous,"CANCELLED");return document
    if document.status!="POSTED":raise ValidationError("Only active documents can be cancelled.")
    original=StockTransaction.objects.get(reference_type=document.__class__.__name__,reference_id=document.pk,is_reversal=False)
    item=document.raw_material or document.finished_product
    original_was_in=original.quantity_in>0
    number=getattr(document,"document_number",None) or document.adjustment_number
    reversal,balance=post_movement(item=item,location=document.location,quantity=document.quantity,direction="OUT" if original_was_in else "IN",
        transaction_number=f"{number}-REV",transaction_type="STOCK_ADJUSTMENT_OUT" if original_was_in else ("STOCK_ADJUSTMENT_IN" if isinstance(document,StockAdjustment) else "WASTAGE_REVERSAL"),
        reference_type=document.__class__.__name__,reference_id=document.pk,unit=document.unit,user=user,
        incoming_unit_cost=original.unit_cost if not original_was_in else None,outgoing_unit_cost=original.unit_cost if original_was_in else None,
        remarks=f"Reversal: {reason}",reversal_of=original,is_reversal=True,audit_action="Cancel")
    document.status="CANCELLED";document.cancelled_by=user;document.cancelled_at=timezone.now();document.cancellation_reason=reason;document.reversal_reference=reversal
    if isinstance(document,StockAdjustment):document.resulting_quantity=balance.current_quantity
    document.save();return document
