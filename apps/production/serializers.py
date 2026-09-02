from django.utils import timezone
from rest_framework.serializers import ModelSerializer
from .models import ProductionBatch
class ProductionBatchSerializer(ModelSerializer):
 class Meta:
  model=ProductionBatch;fields="__all__";read_only_fields=("status","recipe_version","material_cost","total_production_cost","cost_per_unit","posted_at","posted_by","created_by","updated_by")
  extra_kwargs={"batch_number":{"required":False,"allow_blank":True},"manufacturing_date":{"required":False},"expiry_date":{"required":False,"allow_null":True}}
 def create(self,validated_data):
  validated_data.setdefault("manufacturing_date",timezone.localdate())
  validated_data.setdefault("batch_number",f"HIST-{timezone.now().strftime('%Y%m%d%H%M%S%f')}")
  return super().create(validated_data)
