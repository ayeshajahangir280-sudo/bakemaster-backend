from rest_framework import serializers
from .models import StockAdjustment, StockTransaction, WastageDocument
class StockTransactionSerializer(serializers.ModelSerializer):
 class Meta:
  model=StockTransaction
  fields="__all__"
  read_only_fields=tuple(field.name for field in StockTransaction._meta.fields)

class StockDocumentSerializer(serializers.ModelSerializer):
 def validate(self,data):
  rm=data.get("raw_material",getattr(self.instance,"raw_material",None));fg=data.get("finished_product",getattr(self.instance,"finished_product",None))
  if bool(rm)==bool(fg):raise serializers.ValidationError("Select exactly one raw material or finished product.")
  if not str(data.get("reason",getattr(self.instance,"reason",""))).strip():raise serializers.ValidationError({"reason":"Reason is required."})
  if self.instance and self.instance.status!="DRAFT":raise serializers.ValidationError("Only draft documents can be edited.")
  return data

class WastageDocumentSerializer(StockDocumentSerializer):
 class Meta:
  model=WastageDocument;fields="__all__"
  read_only_fields=("document_number","status","unit_cost","total_value","created_by","submitted_by","submitted_at","approved_by","approved_at","posted_by","posted_at","cancelled_by","cancelled_at","cancellation_reason","reversal_reference")

class StockAdjustmentSerializer(StockDocumentSerializer):
 class Meta:
  model=StockAdjustment;fields="__all__"
  read_only_fields=("adjustment_number","status","total_value","previous_quantity","resulting_quantity","created_by","submitted_by","submitted_at","approved_by","approved_at","posted_by","posted_at","cancelled_by","cancelled_at","cancellation_reason","reversal_reference")
 def validate(self,data):
  data=super().validate(data)
  if data.get("direction",getattr(self.instance,"direction",None))=="POSITIVE" and data.get("unit_cost",getattr(self.instance,"unit_cost",None)) is None:raise serializers.ValidationError({"unit_cost":"Unit cost is required for positive adjustments."})
  return data
