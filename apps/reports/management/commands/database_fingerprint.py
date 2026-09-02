import json
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.inventory.models import InventoryBalance, StockTransaction
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice


class Command(BaseCommand):
    def add_arguments(self, parser): parser.add_argument("--output", required=True)
    def handle(self, *args, **options):
        counts={m._meta.label_lower:m._base_manager.count() for m in apps.get_models() if not m._meta.proxy}
        def total(model,field): return str(model.objects.aggregate(v=Sum(field))["v"] or Decimal("0"))
        result={"counts":dict(sorted(counts.items())),"totals":{"inventory_quantity":total(InventoryBalance,"current_quantity"),"inventory_value":total(InventoryBalance,"inventory_value"),"stock_in":total(StockTransaction,"quantity_in"),"stock_out":total(StockTransaction,"quantity_out"),"sales_outstanding":total(SalesInvoice,"outstanding_amount"),"purchase_outstanding":total(PurchaseInvoice,"outstanding_amount")}}
        with open(options["output"],"w",encoding="utf-8") as target:json.dump(result,target,sort_keys=True,indent=2)
