from rest_framework import serializers
from .models import PurchaseInvoice,PurchaseInvoiceItem
class PurchaseItemSerializer(serializers.ModelSerializer):
 class Meta: model=PurchaseInvoiceItem; exclude=("purchase_invoice",); read_only_fields=("tax_amount","line_total")
class PurchaseSerializer(serializers.ModelSerializer):
 items=PurchaseItemSerializer(many=True)
 class Meta: model=PurchaseInvoice; fields="__all__"; read_only_fields=("status","subtotal","discount_total","vat_total","grand_total","paid_amount","outstanding_amount","posted_at","posted_by","cancelled_at","cancelled_by","created_by","updated_by")
 def create(self,data):
  items=data.pop("items",[]); inv=PurchaseInvoice.objects.create(**data)
  for x in items: PurchaseInvoiceItem.objects.create(purchase_invoice=inv,**x)
  return inv
 def update(self,instance,data):
  items=data.pop("items",None)
  instance=super().update(instance,data)
  if items is not None:
   instance.items.all().delete()
   for x in items: PurchaseInvoiceItem.objects.create(purchase_invoice=instance,**x)
  return instance
