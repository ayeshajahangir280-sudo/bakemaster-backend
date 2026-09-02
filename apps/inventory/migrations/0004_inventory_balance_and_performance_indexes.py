from decimal import Decimal
import uuid
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q

def backfill_balances(apps,schema_editor):
    Stock=apps.get_model("inventory","StockTransaction");Balance=apps.get_model("inventory","InventoryBalance")
    totals={}
    for row in Stock.objects.order_by("transaction_date","created_at","id").iterator(chunk_size=2000):
        item_type="RM" if row.raw_material_id else "FG";item_id=row.raw_material_id or row.finished_product_id
        if row.destination_location_id and row.quantity_in:
            key=(item_type,item_id,row.destination_location_id);q,v=totals.get(key,(Decimal("0"),Decimal("0")));totals[key]=(q+row.quantity_in,v+abs(row.total_value))
        if row.source_location_id and row.quantity_out:
            key=(item_type,item_id,row.source_location_id);q,v=totals.get(key,(Decimal("0"),Decimal("0")));totals[key]=(q-row.quantity_out,v-abs(row.total_value))
    for (kind,item_id,location_id),(quantity,value) in totals.items():
        if quantity<0:raise RuntimeError(f"Cannot backfill negative inventory for {kind} {item_id} at {location_id}")
        value=max(Decimal("0"),value);average=value/quantity if quantity else Decimal("0")
        Balance.objects.update_or_create(raw_material_id=item_id if kind=="RM" else None,finished_product_id=item_id if kind=="FG" else None,location_id=location_id,defaults={"current_quantity":quantity,"inventory_value":value,"average_unit_cost":average,"revision":0})

class Migration(migrations.Migration):
 dependencies=[("inventory","0003_opening_stock_and_ledger_direction"),("locations","0001_initial"),("master_data","0001_initial")]
 operations=[
  migrations.CreateModel(name="InventoryBalance",fields=[("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),("current_quantity",models.DecimalField(decimal_places=3,default=0,max_digits=18)),("inventory_value",models.DecimalField(decimal_places=4,default=0,max_digits=18)),("average_unit_cost",models.DecimalField(decimal_places=4,default=0,max_digits=18)),("revision",models.PositiveBigIntegerField(default=0)),("updated_at",models.DateTimeField(auto_now=True)),("finished_product",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to="master_data.finishedproduct")),("location",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="inventory_balances",to="locations.location")),("raw_material",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to="master_data.rawmaterial"))],options={"indexes":[models.Index(fields=["location","updated_at"],name="balance_location_updated_idx")],"constraints":[models.CheckConstraint(condition=Q(raw_material__isnull=False,finished_product__isnull=True)|Q(raw_material__isnull=True,finished_product__isnull=False),name="balance_exactly_one_item"),models.CheckConstraint(condition=Q(current_quantity__gte=0),name="balance_nonnegative_quantity"),models.CheckConstraint(condition=Q(inventory_value__gte=0),name="balance_nonnegative_value"),models.UniqueConstraint(condition=Q(raw_material__isnull=False),fields=("raw_material","location"),name="unique_rm_location_balance"),models.UniqueConstraint(condition=Q(finished_product__isnull=False),fields=("finished_product","location"),name="unique_fg_location_balance")]}),
  migrations.RunPython(backfill_balances,migrations.RunPython.noop),
  migrations.AddIndex(model_name="stocktransaction",index=models.Index(fields=["transaction_type","transaction_date"],name="stock_type_date_idx")),
  migrations.AddIndex(model_name="stocktransaction",index=models.Index(fields=["source_location","transaction_date"],name="stock_source_date_idx")),
  migrations.AddIndex(model_name="stocktransaction",index=models.Index(fields=["destination_location","transaction_date"],name="stock_dest_date_idx")),
 ]
