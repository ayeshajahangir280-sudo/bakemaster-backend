from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q,F
from common.models import UUIDModel
from common.models import TransactionalModel

class StockDocumentBase(TransactionalModel):
    STATUS_CHOICES=[("DRAFT","Draft"),("SUBMITTED","Submitted"),("APPROVED","Approved"),("POSTED","Posted"),("CANCELLED","Cancelled")]
    raw_material=models.ForeignKey("master_data.RawMaterial",null=True,blank=True,on_delete=models.PROTECT)
    finished_product=models.ForeignKey("master_data.FinishedProduct",null=True,blank=True,on_delete=models.PROTECT)
    location=models.ForeignKey("locations.Location",on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=18,decimal_places=3)
    unit=models.ForeignKey("master_data.UnitOfMeasurement",on_delete=models.PROTECT)
    unit_cost=models.DecimalField(max_digits=18,decimal_places=4,default=0)
    total_value=models.DecimalField(max_digits=18,decimal_places=4,default=0)
    reason=models.CharField(max_length=255)
    notes=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=STATUS_CHOICES,default="DRAFT")
    submitted_at=models.DateTimeField(null=True,blank=True)
    submitted_by=models.ForeignKey("accounts.User",null=True,blank=True,on_delete=models.SET_NULL,related_name="submitted_%(class)ss")
    approved_at=models.DateTimeField(null=True,blank=True)
    approved_by=models.ForeignKey("accounts.User",null=True,blank=True,on_delete=models.SET_NULL,related_name="approved_%(class)ss")
    reversal_reference=models.ForeignKey("inventory.StockTransaction",null=True,blank=True,on_delete=models.PROTECT,related_name="+")
    class Meta:
        abstract=True
        constraints=[
            models.CheckConstraint(condition=(Q(raw_material__isnull=False,finished_product__isnull=True)|Q(raw_material__isnull=True,finished_product__isnull=False)),name="%(class)s_exactly_one_item"),
            models.CheckConstraint(condition=Q(quantity__gt=0),name="%(class)s_positive_quantity"),
        ]

class WastageDocument(StockDocumentBase):
    document_number=models.CharField(max_length=80,unique=True,editable=False)
    wastage_date=models.DateField()

class StockAdjustment(StockDocumentBase):
    DIRECTION_CHOICES=[("POSITIVE","Positive"),("NEGATIVE","Negative")]
    adjustment_number=models.CharField(max_length=80,unique=True,editable=False)
    adjustment_date=models.DateField()
    direction=models.CharField(max_length=10,choices=DIRECTION_CHOICES)
    previous_quantity=models.DecimalField(max_digits=18,decimal_places=3,null=True,blank=True)
    resulting_quantity=models.DecimalField(max_digits=18,decimal_places=3,null=True,blank=True)
class InventoryBalance(UUIDModel):
    raw_material=models.ForeignKey("master_data.RawMaterial",null=True,blank=True,on_delete=models.PROTECT)
    finished_product=models.ForeignKey("master_data.FinishedProduct",null=True,blank=True,on_delete=models.PROTECT)
    location=models.ForeignKey("locations.Location",on_delete=models.PROTECT,related_name="inventory_balances")
    current_quantity=models.DecimalField(max_digits=18,decimal_places=3,default=0)
    inventory_value=models.DecimalField(max_digits=18,decimal_places=4,default=0)
    average_unit_cost=models.DecimalField(max_digits=18,decimal_places=4,default=0)
    revision=models.PositiveBigIntegerField(default=0)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
      constraints=[
       models.CheckConstraint(condition=(Q(raw_material__isnull=False,finished_product__isnull=True)|Q(raw_material__isnull=True,finished_product__isnull=False)),name="balance_exactly_one_item"),
       models.CheckConstraint(condition=Q(current_quantity__gte=0),name="balance_nonnegative_quantity"),
       models.CheckConstraint(condition=Q(inventory_value__gte=0),name="balance_nonnegative_value"),
       models.UniqueConstraint(fields=["raw_material","location"],condition=Q(raw_material__isnull=False),name="unique_rm_location_balance"),
       models.UniqueConstraint(fields=["finished_product","location"],condition=Q(finished_product__isnull=False),name="unique_fg_location_balance"),
      ]
      indexes=[models.Index(fields=["location","updated_at"],name="balance_location_updated_idx")]
class StockTransaction(UUIDModel):
    TYPES=[(x,x.replace("_"," ").title()) for x in ("OPENING_STOCK","OPENING_STOCK_REVERSAL","PURCHASE","PURCHASE_REVERSAL","RAW_MATERIAL_TRANSFER_OUT","RAW_MATERIAL_TRANSFER_IN","PRODUCTION_CONSUMPTION","PRODUCTION_OUTPUT","FINISHED_GOODS_TRANSFER_OUT","FINISHED_GOODS_TRANSFER_IN","IN_TRANSIT_OUT","IN_TRANSIT_IN","SALE","SALE_REVERSAL","SALES_RETURN","WASTAGE","WASTAGE_REVERSAL","DAMAGE","EXPIRY","STOCK_ADJUSTMENT_IN","STOCK_ADJUSTMENT_OUT")]
    transaction_number=models.CharField(max_length=80,unique=True); transaction_date=models.DateTimeField(); transaction_type=models.CharField(max_length=40,choices=TYPES); reference_type=models.CharField(max_length=80); reference_id=models.UUIDField(); raw_material=models.ForeignKey("master_data.RawMaterial",null=True,blank=True,on_delete=models.PROTECT); finished_product=models.ForeignKey("master_data.FinishedProduct",null=True,blank=True,on_delete=models.PROTECT); batch=models.CharField(max_length=100,blank=True); source_location=models.ForeignKey("locations.Location",null=True,blank=True,on_delete=models.PROTECT,related_name="stock_out_transactions"); destination_location=models.ForeignKey("locations.Location",null=True,blank=True,on_delete=models.PROTECT,related_name="stock_in_transactions"); quantity_in=models.DecimalField(max_digits=18,decimal_places=3,default=0); quantity_out=models.DecimalField(max_digits=18,decimal_places=3,default=0); unit=models.ForeignKey("master_data.UnitOfMeasurement",on_delete=models.PROTECT); unit_cost=models.DecimalField(max_digits=18,decimal_places=4,default=0); total_value=models.DecimalField(max_digits=18,decimal_places=2,default=0); remarks=models.TextField(blank=True); created_by=models.ForeignKey("accounts.User",null=True,on_delete=models.SET_NULL); created_at=models.DateTimeField(auto_now_add=True); reversal_of=models.OneToOneField("self",null=True,blank=True,on_delete=models.PROTECT,related_name="reversal"); is_reversal=models.BooleanField(default=False)
    class Meta:
      constraints=[models.CheckConstraint(condition=(Q(raw_material__isnull=False,finished_product__isnull=True)|Q(raw_material__isnull=True,finished_product__isnull=False)),name="stock_exactly_one_item"),models.CheckConstraint(condition=Q(quantity_in__gte=0,quantity_out__gte=0),name="stock_nonnegative_quantities"),models.CheckConstraint(condition=(Q(quantity_in__gt=0,quantity_out=0)|Q(quantity_in=0,quantity_out__gt=0)),name="stock_one_direction")]
      indexes=[models.Index(fields=["raw_material","destination_location"]),models.Index(fields=["finished_product","destination_location"],name="inventory_fg_location_idx"),models.Index(fields=["reference_type","reference_id"]),models.Index(fields=["transaction_type","transaction_date"],name="stock_type_date_idx"),models.Index(fields=["source_location","transaction_date"],name="stock_source_date_idx"),models.Index(fields=["destination_location","transaction_date"],name="stock_dest_date_idx")]
    def save(self,*a,**kw):
      if self.pk and StockTransaction.objects.filter(pk=self.pk).exists(): raise ValidationError("Stock ledger entries are immutable.")
      super().save(*a,**kw)
    def delete(self,*a,**kw): raise ValidationError("Stock ledger entries cannot be deleted.")
