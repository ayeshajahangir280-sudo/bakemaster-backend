from django.db import models
from common.models import AuditedModel,UUIDModel
class Recipe(AuditedModel):
 recipe_number=models.CharField(max_length=50,unique=True); finished_product=models.ForeignKey("master_data.FinishedProduct",on_delete=models.PROTECT); standard_output_quantity=models.DecimalField(max_digits=18,decimal_places=3); output_unit=models.ForeignKey("master_data.UnitOfMeasurement",on_delete=models.PROTECT); version=models.CharField(max_length=30); effective_date=models.DateField(); status=models.CharField(max_length=20,default="DRAFT",choices=[("DRAFT","Draft"),("ACTIVE","Active"),("INACTIVE","Inactive"),("ARCHIVED","Archived")]); is_default=models.BooleanField(default=False); notes=models.TextField(blank=True)
 class Meta: constraints=[models.UniqueConstraint(fields=["finished_product"],condition=models.Q(is_default=True,status="ACTIVE"),name="one_default_active_recipe")]
 @property
 def total_material_cost(self): return sum((i.required_quantity*i.unit_cost_snapshot for i in self.items.all()),0)
 @property
 def cost_per_output_unit(self): return self.total_material_cost/self.standard_output_quantity if self.standard_output_quantity else 0
class RecipeItem(UUIDModel):
 recipe=models.ForeignKey(Recipe,on_delete=models.CASCADE,related_name="items"); raw_material=models.ForeignKey("master_data.RawMaterial",on_delete=models.PROTECT); required_quantity=models.DecimalField(max_digits=18,decimal_places=3); unit=models.ForeignKey("master_data.UnitOfMeasurement",on_delete=models.PROTECT); wastage_percentage=models.DecimalField(max_digits=7,decimal_places=3,default=0); unit_cost_snapshot=models.DecimalField(max_digits=18,decimal_places=4,default=0)
