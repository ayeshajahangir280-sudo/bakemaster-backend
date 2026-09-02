from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [
        migrations.RemoveIndex(
            model_name="stocktransaction",
            name="inventory_s_finishe_be362b_idx",
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(
                fields=["finished_product", "destination_location"],
                name="inventory_fg_location_idx",
            ),
        ),
    ]
