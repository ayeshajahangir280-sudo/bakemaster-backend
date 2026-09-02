from rest_framework import serializers
from .models import SalesInvoice,SalesInvoiceItem,SalesReturn,SalesReturnItem
class SalesItemSerializer(serializers.ModelSerializer):
 class Meta:model=SalesInvoiceItem;exclude=("sales_invoice",);read_only_fields=("unit_cost_snapshot","tax_amount","line_total","cost_total","gross_profit")
class SalesInvoiceSerializer(serializers.ModelSerializer):
 items=SalesItemSerializer(many=True)
 class Meta:model=SalesInvoice;fields="__all__";read_only_fields=("status","subtotal","discount_total","vat_total","grand_total","cost_of_goods_sold","gross_profit","gross_margin_percentage","paid_amount","outstanding_amount","created_by","updated_by")
 def create(self,data):
  items=data.pop("items",[]);obj=SalesInvoice.objects.create(**data)
  for i in items:SalesInvoiceItem.objects.create(sales_invoice=obj,**i)
  return obj
 def update(self,instance,data):
  items=data.pop("items",None);obj=super().update(instance,data)
  if items is not None:
   obj.items.all().delete()
   for i in items:SalesInvoiceItem.objects.create(sales_invoice=obj,**i)
  return obj
class SalesReturnItemSerializer(serializers.ModelSerializer):
 class Meta:model=SalesReturnItem;exclude=("sales_return",);read_only_fields=("finished_product","batch","sold_quantity","previously_returned_quantity","unit_price","credit_amount")
class SalesReturnSerializer(serializers.ModelSerializer):
 items=SalesReturnItemSerializer(many=True)
 class Meta:model=SalesReturn;fields="__all__";read_only_fields=("return_number","customer","status","subtotal","vat_total","credit_total","posted_at","posted_by","cancelled_at","cancelled_by","created_by","updated_by")
 def create(self,data):
  items=data.pop("items",[])
  if not items:raise serializers.ValidationError("At least one return line is required.")
  invoice=data["original_sales_invoice"];obj=SalesReturn.objects.create(customer=invoice.customer,**data)
  for item in items:
   original=item["original_sales_invoice_item"]
   if original.sales_invoice_id!=invoice.id:raise serializers.ValidationError("Return line does not belong to the selected invoice.")
   SalesReturnItem.objects.create(sales_return=obj,finished_product=original.finished_product,batch="",sold_quantity=original.quantity,unit_price=original.selling_price,credit_amount=0,**item)
  return obj
