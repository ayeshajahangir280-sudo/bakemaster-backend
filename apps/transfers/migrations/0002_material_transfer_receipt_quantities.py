from django.db import migrations,models
class Migration(migrations.Migration):
 dependencies=[("transfers","0001_initial")]
 operations=[
  migrations.AddField(model_name="materialtransferitem",name="dispatched_quantity",field=models.DecimalField(decimal_places=3,default=0,max_digits=18)),
  migrations.AddField(model_name="materialtransferitem",name="received_quantity",field=models.DecimalField(decimal_places=3,default=0,max_digits=18)),
  migrations.AddField(model_name="materialtransferitem",name="damaged_quantity",field=models.DecimalField(decimal_places=3,default=0,max_digits=18)),
 ]
