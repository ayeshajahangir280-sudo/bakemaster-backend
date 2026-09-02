from django.db import migrations, models
from django.db.models import Q


def classify_existing_opening_stock(apps, schema_editor):
    StockTransaction = apps.get_model("inventory", "StockTransaction")
    StockTransaction.objects.filter(
        reference_type__in=["OpeningRawMaterial", "OpeningFinishedGoods"]
    ).update(reference_type="OpeningStock", transaction_type="OPENING_STOCK")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_combined_product_location_stock")]

    operations = [
        migrations.RunPython(classify_existing_opening_stock, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="stocktransaction",
            constraint=models.CheckConstraint(
                condition=(Q(quantity_in__gt=0, quantity_out=0) | Q(quantity_in=0, quantity_out__gt=0)),
                name="stock_one_direction",
            ),
        ),
        migrations.AlterField(
            model_name="stocktransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    (value, value.replace("_", " ").title())
                    for value in (
                        "OPENING_STOCK", "OPENING_STOCK_REVERSAL", "PURCHASE", "PURCHASE_REVERSAL",
                        "RAW_MATERIAL_TRANSFER_OUT", "RAW_MATERIAL_TRANSFER_IN", "PRODUCTION_CONSUMPTION",
                        "PRODUCTION_OUTPUT", "FINISHED_GOODS_TRANSFER_OUT", "FINISHED_GOODS_TRANSFER_IN",
                        "IN_TRANSIT_OUT", "IN_TRANSIT_IN", "SALE", "SALE_REVERSAL", "SALES_RETURN",
                        "WASTAGE", "DAMAGE", "EXPIRY", "STOCK_ADJUSTMENT_IN", "STOCK_ADJUSTMENT_OUT",
                    )
                ],
                max_length=40,
            ),
        ),
    ]
