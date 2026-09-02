from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.inventory.models import StockTransaction
from apps.inventory.posting import post_movement
from apps.locations.models import Location
from .models import MaterialTransfer,FinishedGoodsTransfer

def _virtual(kind):
 code="SYS-TRANSIT" if kind=="IN_TRANSIT" else "SYS-DAMAGED"
 return Location.objects.get_or_create(code=code,defaults={"name":"In Transit" if kind=="IN_TRANSIT" else "Damaged Stock","location_type":kind,"is_inventory_location":True})[0]
def _transition(obj,allowed,status,user,field=None):
 if obj.status not in allowed:raise ValidationError(f"Action is not allowed while status is {obj.status}.")
 obj.status=status
 if field:setattr(obj,field,user)
 obj.save();return obj
@transaction.atomic
def dispatch(transfer,user,finished=False):
 transfer=transfer.__class__.objects.select_for_update().prefetch_related("items").get(pk=transfer.pk)
 if transfer.status not in ({"APPROVED"} if finished else {"APPROVED","SUBMITTED"}):raise ValidationError("Transfer is not ready for dispatch.")
 transit=_virtual("IN_TRANSIT")
 for line in transfer.items.all():
  qty=line.requested_quantity if finished else line.quantity
  if qty<=0:raise ValidationError("Transfer quantities must be positive.")
  item=line.finished_product if finished else line.raw_material
  out,_=post_movement(item=item,location=transfer.source_location,quantity=qty,direction="OUT",transaction_number=f"{transfer.transfer_number}-{line.id}-OUT",transaction_type="FINISHED_GOODS_TRANSFER_OUT" if finished else "RAW_MATERIAL_TRANSFER_OUT",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=line.unit,user=user,audit_action="Dispatch",audit_module="transfers")
  post_movement(item=item,location=transit,quantity=qty,direction="IN",transaction_number=f"{transfer.transfer_number}-{line.id}-TRANSIT",transaction_type="IN_TRANSIT_IN",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=line.unit,user=user,incoming_unit_cost=out.unit_cost,audit_action="Dispatch",audit_module="transfers")
  line.dispatched_quantity=qty;line.save(update_fields=["dispatched_quantity"])
 transfer.status="IN_TRANSIT" if finished else "DISPATCHED";transfer.posted_at=timezone.now();transfer.posted_by=user
 if hasattr(transfer,"dispatched_by"):transfer.dispatched_by=user
 if hasattr(transfer,"dispatch_date"):transfer.dispatch_date=timezone.localdate()
 transfer.save();return transfer
@transaction.atomic
def receive(transfer,user,lines,finished=False):
 transfer=transfer.__class__.objects.select_for_update().prefetch_related("items").get(pk=transfer.pk)
 if transfer.status not in ({"IN_TRANSIT","PARTIALLY_RECEIVED"} if finished else {"DISPATCHED","PARTIALLY_RECEIVED"}):raise ValidationError("Transfer is not in transit.")
 transit=_virtual("IN_TRANSIT");damaged_location=_virtual("DAMAGED_GOODS");payload={str(x.get("id")):x for x in lines}
 complete=True
 for line in transfer.items.all():
  data=payload.get(str(line.id),{});received=Decimal(str(data.get("received_quantity",0)));damaged=Decimal(str(data.get("damaged_quantity",0)))
  remaining=line.dispatched_quantity-line.received_quantity-line.damaged_quantity
  if received<0 or damaged<0 or received+damaged>remaining:raise ValidationError("Receipt exceeds the remaining in-transit quantity.")
  item=line.finished_product if finished else line.raw_material
  if received+damaged:
   out,_=post_movement(item=item,location=transit,quantity=received+damaged,direction="OUT",transaction_number=f"{transfer.transfer_number}-{line.id}-TO-{line.received_quantity+line.damaged_quantity}",transaction_type="IN_TRANSIT_OUT",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=line.unit,user=user,audit_action="Receive",audit_module="transfers")
   if received:post_movement(item=item,location=transfer.destination_location,quantity=received,direction="IN",transaction_number=f"{transfer.transfer_number}-{line.id}-IN-{line.received_quantity}",transaction_type="FINISHED_GOODS_TRANSFER_IN" if finished else "RAW_MATERIAL_TRANSFER_IN",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=line.unit,user=user,incoming_unit_cost=out.unit_cost,audit_action="Receive",audit_module="transfers")
   if damaged:post_movement(item=item,location=damaged_location,quantity=damaged,direction="IN",transaction_number=f"{transfer.transfer_number}-{line.id}-DMG-{line.damaged_quantity}",transaction_type="DAMAGE",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=line.unit,user=user,incoming_unit_cost=out.unit_cost,audit_action="Receive damaged",audit_module="transfers")
  line.received_quantity+=received;line.damaged_quantity+=damaged;line.save(update_fields=["received_quantity","damaged_quantity"])
  if line.received_quantity+line.damaged_quantity<line.dispatched_quantity:complete=False
 transfer.status="RECEIVED" if complete else "PARTIALLY_RECEIVED"
 if hasattr(transfer,"received_by"):transfer.received_by=user
 if hasattr(transfer,"received_date"):transfer.received_date=timezone.localdate()
 transfer.save();return transfer

@transaction.atomic
def cancel_transfer(transfer,user,reason):
 if not str(reason).strip():raise ValidationError("Cancellation reason is required.")
 transfer=transfer.__class__.objects.select_for_update().get(pk=transfer.pk)
 if transfer.status=="CANCELLED":return transfer
 if transfer.status in {"DRAFT","SUBMITTED","APPROVED"}:
  transfer.status="CANCELLED";transfer.cancelled_at=timezone.now();transfer.cancelled_by=user;transfer.cancellation_reason=reason;transfer.save();return transfer
 originals=list(StockTransaction.objects.select_for_update().filter(reference_type=transfer.__class__.__name__,reference_id=transfer.id,is_reversal=False).order_by("-created_at","-id"))
 for original in originals:
  if hasattr(original,"reversal"):raise ValidationError("Transfer has already been reversed.")
  item=original.raw_material or original.finished_product
  if original.quantity_in:
   location=original.destination_location;direction="OUT";quantity=original.quantity_in
   incoming_cost=None;outgoing_cost=original.unit_cost
  else:
   location=original.source_location;direction="IN";quantity=original.quantity_out
   incoming_cost=original.unit_cost;outgoing_cost=None
  post_movement(item=item,location=location,quantity=quantity,direction=direction,transaction_number=f"REV-{original.transaction_number}",transaction_type="STOCK_ADJUSTMENT_OUT" if direction=="OUT" else "STOCK_ADJUSTMENT_IN",reference_type=transfer.__class__.__name__,reference_id=transfer.id,unit=original.unit,user=user,incoming_unit_cost=incoming_cost,outgoing_unit_cost=outgoing_cost,remarks=f"Transfer cancellation: {reason}",reversal_of=original,is_reversal=True,audit_action="Cancel",audit_module="transfers")
 transfer.status="CANCELLED";transfer.cancelled_at=timezone.now();transfer.cancelled_by=user;transfer.cancellation_reason=reason;transfer.save();return transfer
