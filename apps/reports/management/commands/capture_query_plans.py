from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.inventory.models import InventoryBalance, StockTransaction
from apps.payments.models import CustomerPayment, SupplierPayment
from apps.production.models import ProductionBatch
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import CustomerLedger, SalesInvoice


class Command(BaseCommand):
    def add_arguments(self, parser): parser.add_argument("--output", required=True)
    def handle(self,*args,**options):
        queries={
            "inventory-balances":InventoryBalance.objects.select_related("raw_material","finished_product","location"),
            "stock-ledger":StockTransaction.objects.select_related("raw_material","finished_product","source_location","destination_location").order_by("-transaction_date")[:1000],
            "inventory-valuation":InventoryBalance.objects.filter(current_quantity__gt=0),
            "sales":SalesInvoice.objects.select_related("customer","sales_location").order_by("-invoice_date")[:1000],
            "purchases":PurchaseInvoice.objects.select_related("supplier","warehouse").order_by("-invoice_date")[:1000],
            "production":ProductionBatch.objects.select_related("recipe","finished_product").order_by("-manufacturing_date")[:1000],
            "outstanding":CustomerLedger.objects.filter(Q(debit__gt=0)|Q(credit__gt=0))[:1000],
            "customer-payments":CustomerPayment.objects.prefetch_related("allocations")[:1000],
            "supplier-payments":SupplierPayment.objects.prefetch_related("allocations")[:1000],
        }
        with open(options["output"],"w",encoding="utf-8") as target:
            for name,query in queries.items():
                target.write(f"=== {name} ===\n{query.explain(analyze=True,buffers=True,verbose=False)}\n\n")
