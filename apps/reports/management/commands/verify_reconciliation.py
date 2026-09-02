from django.core.management.base import BaseCommand,CommandError
from apps.inventory.posting import reconciliation_discrepancies
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice

class Command(BaseCommand):
 help="Fail when inventory or financial normalized balances are invalid."
 def handle(self,*args,**options):
  inventory=reconciliation_discrepancies();negative_sales=SalesInvoice.objects.filter(outstanding_amount__lt=0).count();negative_purchases=PurchaseInvoice.objects.filter(outstanding_amount__lt=0).count()
  if inventory or negative_sales or negative_purchases:raise CommandError(f"Reconciliation failed: inventory={len(inventory)}, negative_sales={negative_sales}, negative_purchases={negative_purchases}")
  self.stdout.write(self.style.SUCCESS("Inventory and financial reconciliation passed."))
