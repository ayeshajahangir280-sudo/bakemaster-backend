from django.db import transaction
from rest_framework import serializers
from .models import MaterialTransfer,MaterialTransferItem,FinishedGoodsTransfer,FinishedGoodsTransferItem

class MaterialTransferItemSerializer(serializers.ModelSerializer):
 class Meta:model=MaterialTransferItem;exclude=("transfer",);read_only_fields=("dispatched_quantity","received_quantity","damaged_quantity")
class MaterialTransferSerializer(serializers.ModelSerializer):
 items=MaterialTransferItemSerializer(many=True)
 class Meta:model=MaterialTransfer;fields="__all__";read_only_fields=("transfer_number","status","requested_by","approved_by","dispatched_by","received_by","posted_at","posted_by","cancelled_at","cancelled_by","created_by","updated_by")
 @transaction.atomic
 def create(self,data):
  items=data.pop("items",[])
  if not items:raise serializers.ValidationError("At least one transfer item is required.")
  obj=MaterialTransfer.objects.create(requested_by=self.context["request"].user,**data)
  for item in items:MaterialTransferItem.objects.create(transfer=obj,**item)
  return obj
 @transaction.atomic
 def update(self,instance,data):
  items=data.pop("items",None);obj=super().update(instance,data)
  if items is not None:
   obj.items.all().delete()
   for item in items:MaterialTransferItem.objects.create(transfer=obj,**item)
  return obj
class FinishedGoodsTransferItemSerializer(serializers.ModelSerializer):
 class Meta:model=FinishedGoodsTransferItem;exclude=("transfer",);read_only_fields=("dispatched_quantity","received_quantity","damaged_quantity");extra_kwargs={"batch":{"required":False,"allow_blank":True}}
class FinishedGoodsTransferSerializer(serializers.ModelSerializer):
 items=FinishedGoodsTransferItemSerializer(many=True)
 class Meta:model=FinishedGoodsTransfer;fields="__all__";read_only_fields=("transfer_number","status","posted_at","posted_by","cancelled_at","cancelled_by","created_by","updated_by")
 @transaction.atomic
 def create(self,data):
  items=data.pop("items",[])
  if not items:raise serializers.ValidationError("At least one transfer item is required.")
  obj=FinishedGoodsTransfer.objects.create(**data)
  for item in items:
   item.pop("batch",None);FinishedGoodsTransferItem.objects.create(transfer=obj,batch="",**item)
  return obj
 @transaction.atomic
 def update(self,instance,data):
  items=data.pop("items",None);obj=super().update(instance,data)
  if items is not None:
   obj.items.all().delete()
   for item in items:
    item.pop("batch",None);FinishedGoodsTransferItem.objects.create(transfer=obj,batch="",**item)
  return obj
