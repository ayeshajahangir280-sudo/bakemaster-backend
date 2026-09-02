from django.db import models
from common.models import AuditedModel
class Location(AuditedModel):
    class Type(models.TextChoices):
        RAW_MATERIAL_WAREHOUSE="RAW_MATERIAL_WAREHOUSE"; PRODUCTION="PRODUCTION"; FINISHED_GOODS_WAREHOUSE="FINISHED_GOODS_WAREHOUSE"; SHOP="SHOP"; DELIVERY_VAN="DELIVERY_VAN"; DAMAGED_GOODS="DAMAGED_GOODS"; IN_TRANSIT="IN_TRANSIT"; OTHER="OTHER"
    code=models.CharField(max_length=30,unique=True); name=models.CharField(max_length=120); location_type=models.CharField(max_length=40,choices=Type.choices); address=models.TextField(blank=True); is_sales_location=models.BooleanField(default=False); is_inventory_location=models.BooleanField(default=True); is_production_location=models.BooleanField(default=False); is_active=models.BooleanField(default=True)
    def __str__(self): return self.name
