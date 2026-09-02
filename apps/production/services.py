from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inventory.models import StockTransaction
from apps.inventory.services import get_available_stock, get_average_cost
from apps.inventory.posting import post_movement
from .models import ProductionBatch, ProductionConsumption, ProductionOutput


@transaction.atomic
def complete_production(pk, user, actual_quantity=None):
    production = ProductionBatch.objects.select_for_update().select_related(
        "recipe", "finished_product", "finished_product__sales_unit"
    ).get(pk=pk)
    if production.status not in {"DRAFT", "PLANNED", "IN_PROGRESS"}:
        raise ValidationError("Only an unfinished production record can be completed.")
    output = Decimal(str(actual_quantity or production.actual_produced_quantity or production.planned_quantity))
    if output <= 0:
        raise ValidationError("Actual produced quantity must be positive.")
    recipe = production.recipe
    scale = production.planned_quantity / recipe.standard_output_quantity
    requirements = []
    for line in recipe.items.select_related("raw_material", "unit"):
        required = line.required_quantity * scale * (Decimal("1") + line.wastage_percentage / Decimal("100"))
        StockTransaction.objects.select_for_update().filter(
            raw_material=line.raw_material,
            destination_location=production.production_location,
        )
        available = get_available_stock(line.raw_material, production.production_location)
        if required > available:
            raise ValidationError(f"Insufficient {line.raw_material.name}. Available: {available}; required: {required}.")
        requirements.append((line, required, get_average_cost(line.raw_material, production.production_location)))

    material_cost = Decimal("0")
    now = timezone.now()
    for line, required, unit_cost in requirements:
        value = required * unit_cost
        material_cost += value
        consumption = ProductionConsumption.objects.create(
            production_batch=production, raw_material=line.raw_material,
            standard_required_quantity=required, actual_consumed_quantity=required,
            unit=line.unit, unit_cost=unit_cost, total_cost=value, variance_quantity=0,
        )
        post_movement(item=line.raw_material,location=production.production_location,quantity=required,direction="OUT",transaction_number=f"{production.production_number}-CON-{consumption.id}",transaction_type="PRODUCTION_CONSUMPTION",reference_type="ProductionBatch",reference_id=production.id,unit=line.unit,user=user,remarks=production.remarks,audit_module="production")

    total_cost = material_cost + production.additional_cost
    cost_per_unit = total_cost / output
    ProductionOutput.objects.create(production_batch=production, quantity=output, unit_cost=cost_per_unit)
    post_movement(item=production.finished_product,location=production.finished_goods_destination,quantity=output,direction="IN",transaction_number=f"{production.production_number}-OUT",transaction_type="PRODUCTION_OUTPUT",reference_type="ProductionBatch",reference_id=production.id,unit=production.finished_product.sales_unit,user=user,incoming_unit_cost=cost_per_unit,remarks=production.remarks,audit_action="Complete",audit_module="production")
    production.recipe_version = recipe.version
    production.actual_produced_quantity = output
    production.material_cost = material_cost
    production.total_production_cost = total_cost
    production.cost_per_unit = cost_per_unit
    production.status = "COMPLETED"
    production.posted_at = now
    production.posted_by = user
    production.save()
    return production


@transaction.atomic
def reverse_production(pk, user, reason):
    if not str(reason).strip():
        raise ValidationError("Cancellation reason is required.")
    production = ProductionBatch.objects.select_for_update().get(pk=pk)
    if production.status == "CANCELLED":
        return production
    if production.status != "COMPLETED":
        raise ValidationError("Only completed production can be reversed.")
    originals = list(StockTransaction.objects.select_for_update().filter(
        reference_type="ProductionBatch", reference_id=production.id, is_reversal=False
    ))
    for original in originals:
        if hasattr(original, "reversal"):
            raise ValidationError("Production has already been reversed.")
        incoming = original.quantity_out > 0
        item=original.raw_material or original.finished_product;location=original.source_location if incoming else original.destination_location
        post_movement(item=item,location=location,quantity=original.quantity_out if incoming else original.quantity_in,direction="IN" if incoming else "OUT",transaction_number=f"REV-{original.transaction_number}",transaction_type="STOCK_ADJUSTMENT_IN" if incoming else "STOCK_ADJUSTMENT_OUT",reference_type="ProductionBatch",reference_id=production.id,unit=original.unit,user=user,incoming_unit_cost=original.unit_cost if incoming else None,outgoing_unit_cost=original.unit_cost if not incoming else None,remarks=f"Production reversal: {reason}",reversal_of=original,is_reversal=True,audit_action="Reverse",audit_module="production")
    production.status = "CANCELLED"
    production.cancelled_at = timezone.now(); production.cancelled_by = user
    production.cancellation_reason = reason; production.save()
    return production
