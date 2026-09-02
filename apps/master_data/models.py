from decimal import Decimal
from django.db import models
from django.db.models import Q
from common.models import AuditedModel
class ActiveModel(AuditedModel):
    status=models.CharField(max_length=20,default="ACTIVE",choices=[("ACTIVE","Active"),("INACTIVE","Inactive")])
    class Meta: abstract=True
class Supplier(ActiveModel):
    supplier_code=models.CharField(max_length=30,unique=True); name=models.CharField(max_length=160); contact_person=models.CharField(max_length=120,blank=True); phone=models.CharField(max_length=40,blank=True); email=models.EmailField(blank=True); address=models.TextField(blank=True); vat_number=models.CharField(max_length=50,blank=True); opening_balance=models.DecimalField(max_digits=18,decimal_places=2,default=0); payment_terms_days=models.PositiveIntegerField(default=0); credit_limit=models.DecimalField(max_digits=18,decimal_places=2,default=0); notes=models.TextField(blank=True)
class Customer(ActiveModel):
    customer_code=models.CharField(max_length=30,unique=True); name=models.CharField(max_length=160); contact_person=models.CharField(max_length=120,blank=True); phone=models.CharField(max_length=40,blank=True); email=models.EmailField(blank=True); address=models.TextField(blank=True); customer_type=models.CharField(max_length=50,blank=True); vat_number=models.CharField(max_length=50,blank=True); opening_balance=models.DecimalField(max_digits=18,decimal_places=2,default=0); credit_limit=models.DecimalField(max_digits=18,decimal_places=2,default=0); payment_terms_days=models.PositiveIntegerField(default=0); assigned_location=models.ForeignKey("locations.Location",null=True,blank=True,on_delete=models.SET_NULL); notes=models.TextField(blank=True)
class ItemCategory(ActiveModel):
    name=models.CharField(max_length=100); kind=models.CharField(max_length=2,choices=[("RM","Raw material"),("FG","Finished product")])
    class Meta: unique_together=("name","kind")
class UnitOfMeasurement(ActiveModel):
    code=models.CharField(max_length=20,unique=True); name=models.CharField(max_length=60)
class TaxRate(ActiveModel):
    name=models.CharField(max_length=80,unique=True); rate=models.DecimalField(max_digits=7,decimal_places=4,default=0)
class PaymentMethod(ActiveModel): name=models.CharField(max_length=80,unique=True)
class RawMaterial(ActiveModel):
    material_code=models.CharField(max_length=30,unique=True); name=models.CharField(max_length=160); category=models.ForeignKey(ItemCategory,on_delete=models.PROTECT,related_name="raw_materials"); base_unit=models.ForeignKey(UnitOfMeasurement,on_delete=models.PROTECT,related_name="base_materials"); purchase_unit=models.ForeignKey(UnitOfMeasurement,on_delete=models.PROTECT,related_name="purchase_materials"); consumption_unit=models.ForeignKey(UnitOfMeasurement,on_delete=models.PROTECT,related_name="consumption_materials"); conversion_factor=models.DecimalField(max_digits=18,decimal_places=6,default=1); minimum_stock=models.DecimalField(max_digits=18,decimal_places=3,default=0); reorder_level=models.DecimalField(max_digits=18,decimal_places=3,default=0); current_average_cost=models.DecimalField(max_digits=18,decimal_places=4,default=0); tax_rate=models.ForeignKey(TaxRate,null=True,blank=True,on_delete=models.SET_NULL)
class FinishedProduct(ActiveModel):
    product_code=models.CharField(max_length=30,unique=True); name=models.CharField(max_length=160); category=models.ForeignKey(ItemCategory,on_delete=models.PROTECT,related_name="products"); sales_unit=models.ForeignKey(UnitOfMeasurement,on_delete=models.PROTECT); standard_sales_price=models.DecimalField(max_digits=18,decimal_places=2,default=0); standard_cost=models.DecimalField(max_digits=18,decimal_places=4,default=0); minimum_stock=models.DecimalField(max_digits=18,decimal_places=3,default=0); tax_rate=models.ForeignKey(TaxRate,null=True,blank=True,on_delete=models.SET_NULL); barcode=models.CharField(max_length=80,blank=True,unique=True,null=True); shelf_life_days=models.PositiveIntegerField(default=0)
class ShopProductSetting(ActiveModel):
    location=models.ForeignKey("locations.Location",on_delete=models.CASCADE); finished_product=models.ForeignKey(FinishedProduct,on_delete=models.CASCADE); minimum_stock=models.DecimalField(max_digits=18,decimal_places=3,default=0); target_stock=models.DecimalField(max_digits=18,decimal_places=3,default=0); reorder_level=models.DecimalField(max_digits=18,decimal_places=3,default=0); maximum_stock=models.DecimalField(max_digits=18,decimal_places=3,default=0); lead_time_days=models.PositiveIntegerField(default=0)
    class Meta: constraints=[models.UniqueConstraint(fields=["location","finished_product"],name="unique_shop_product")]
