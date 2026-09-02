from decimal import Decimal, ROUND_HALF_UP
from time import sleep

from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditLog
from .models import InventoryBalance, StockTransaction

QTY=Decimal("0.001"); MONEY=Decimal("0.0001"); ZERO=Decimal("0")

def _item_fields(item):
    return {"raw_material":item,"finished_product":None} if item._meta.model_name=="rawmaterial" else {"raw_material":None,"finished_product":item}

def _locked_balance(item,location):
    fields=_item_fields(item); lookup={**fields,"location":location}
    for attempt in range(3):
        try:
            balance,created=InventoryBalance.objects.get_or_create(**lookup)
            balance=InventoryBalance.objects.select_for_update().get(pk=balance.pk)
            if created:
                field="raw_material" if fields["raw_material"] else "finished_product"
                entries=StockTransaction.objects.filter(**{field:item}).filter(Q(source_location=location)|Q(destination_location=location))
                quantity=value=ZERO
                for entry in entries:
                    if entry.destination_location_id==location.id:quantity+=entry.quantity_in;value+=abs(entry.total_value)
                    if entry.source_location_id==location.id:quantity-=entry.quantity_out;value-=abs(entry.total_value)
                if quantity<0:raise ValidationError("Existing ledger contains negative stock and cannot initialize a balance.")
                balance.current_quantity=quantity;balance.inventory_value=max(ZERO,value)
                balance.average_unit_cost=balance.inventory_value/quantity if quantity else ZERO;balance.save()
            return balance
        except IntegrityError:
            if attempt==2:raise
            sleep(0.01*(attempt+1))
    raise RuntimeError("Could not lock inventory balance")

def post_movement(*,item,location,quantity,direction,transaction_number,transaction_type,
                  reference_type,reference_id,unit,user,incoming_unit_cost=None,remarks="",
                  reversal_of=None,is_reversal=False,audit_action="Post",audit_module="inventory",transaction_date=None,outgoing_unit_cost=None):
    quantity=Decimal(str(quantity)).quantize(QTY)
    if quantity<=0:raise ValidationError("Movement quantity must be positive.")
    if direction not in {"IN","OUT"}:raise ValidationError("Movement direction must be IN or OUT.")
    with transaction.atomic():
        balance=_locked_balance(item,location)
        previous=balance.current_quantity
        if direction=="OUT":
            if quantity>previous:
                if reversal_of:
                    field="raw_material" if item._meta.model_name=="rawmaterial" else "finished_product"
                    blocking=StockTransaction.objects.filter(**{field:item},source_location=location,created_at__gt=reversal_of.created_at,is_reversal=False).order_by("-created_at").first()
                    raise ValidationError({"message":"Cancellation is blocked because this stock was used downstream.","blocking_document":blocking.transaction_number if blocking else "Later stock movement","item":getattr(item,"name",str(item)),"location":getattr(location,"name",str(location)),"required_quantity":str(quantity),"available_quantity":str(previous),"required_reversal_order":"Cancel the blocking downstream document first, then retry this cancellation."})
                raise ValidationError(f"Insufficient stock. Available: {previous}; requested: {quantity}.")
            unit_cost=Decimal(str(outgoing_unit_cost)).quantize(MONEY) if outgoing_unit_cost is not None else balance.average_unit_cost
            value=(quantity*unit_cost).quantize(MONEY,rounding=ROUND_HALF_UP)
            balance.current_quantity=(previous-quantity).quantize(QTY)
            balance.inventory_value=max(ZERO,balance.inventory_value-value).quantize(MONEY)
        else:
            if incoming_unit_cost is None:raise ValidationError("Incoming unit cost is required.")
            unit_cost=Decimal(str(incoming_unit_cost)).quantize(MONEY)
            if unit_cost<0:raise ValidationError("Unit cost cannot be negative.")
            value=(quantity*unit_cost).quantize(MONEY,rounding=ROUND_HALF_UP)
            balance.current_quantity=(previous+quantity).quantize(QTY)
            balance.inventory_value=(balance.inventory_value+value).quantize(MONEY)
        balance.average_unit_cost=(balance.inventory_value/balance.current_quantity).quantize(MONEY,rounding=ROUND_HALF_UP) if balance.current_quantity else ZERO
        balance.revision+=1
        balance.save(update_fields=["current_quantity","inventory_value","average_unit_cost","revision","updated_at"])
        fields=_item_fields(item)
        ledger=StockTransaction.objects.create(
            transaction_number=transaction_number,transaction_date=transaction_date or __import__("django.utils.timezone",fromlist=["now"]).now(),
            transaction_type=transaction_type,reference_type=reference_type,reference_id=reference_id,
            source_location=location if direction=="OUT" else None,destination_location=location if direction=="IN" else None,
            quantity_in=quantity if direction=="IN" else ZERO,quantity_out=quantity if direction=="OUT" else ZERO,
            unit=unit,unit_cost=unit_cost,total_value=value,remarks=remarks,created_by=user,
            reversal_of=reversal_of,is_reversal=is_reversal,**fields,
        )
        AuditLog.objects.create(user=user,action=audit_action,module=audit_module,record_type=reference_type,
            record_id=reference_id,record_number=transaction_number,description=f"{direction} {quantity} at {location}",
            previous_values={"quantity":str(previous)},new_values={"quantity":str(balance.current_quantity),"revision":balance.revision})
        return ledger,balance

def reconciliation_discrepancies():
    discrepancies=[]
    for balance in InventoryBalance.objects.select_related("raw_material","finished_product","location"):
        item=balance.raw_material or balance.finished_product
        field="raw_material" if balance.raw_material_id else "finished_product"
        entries=StockTransaction.objects.filter(**{field:item}).filter(Q(source_location=balance.location)|Q(destination_location=balance.location))
        quantity=value=ZERO
        for entry in entries:
            if entry.destination_location_id==balance.location_id:quantity+=entry.quantity_in;value+=abs(entry.total_value)
            if entry.source_location_id==balance.location_id:quantity-=entry.quantity_out;value-=abs(entry.total_value)
        if quantity!=balance.current_quantity or value.quantize(MONEY)!=balance.inventory_value:
            discrepancies.append({"balance_id":str(balance.id),"item_id":str(item.id),"location_id":str(balance.location_id),"ledger_quantity":quantity,"balance_quantity":balance.current_quantity,"ledger_value":value,"balance_value":balance.inventory_value})
    return discrepancies
