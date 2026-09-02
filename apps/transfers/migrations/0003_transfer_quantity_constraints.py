from django.db import migrations,models
class Migration(migrations.Migration):
 dependencies=[("transfers","0002_material_transfer_receipt_quantities")]
 operations=[
  migrations.AddConstraint(model_name="materialtransferitem",constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0,dispatched_quantity__gte=0,received_quantity__gte=0,damaged_quantity__gte=0),name="material_transfer_nonnegative")),
  migrations.AddConstraint(model_name="materialtransferitem",constraint=models.CheckConstraint(condition=models.Q(dispatched_quantity__lte=models.F("quantity")),name="material_dispatch_within_request")),
  migrations.AddConstraint(model_name="materialtransferitem",constraint=models.CheckConstraint(condition=models.Q(received_quantity__lte=models.F("dispatched_quantity")-models.F("damaged_quantity")),name="material_receipt_within_dispatch")),
  migrations.AddConstraint(model_name="finishedgoodstransferitem",constraint=models.CheckConstraint(condition=models.Q(requested_quantity__gt=0,dispatched_quantity__gte=0,received_quantity__gte=0,damaged_quantity__gte=0),name="fg_transfer_nonnegative")),
  migrations.AddConstraint(model_name="finishedgoodstransferitem",constraint=models.CheckConstraint(condition=models.Q(dispatched_quantity__lte=models.F("requested_quantity")),name="fg_dispatch_within_request")),
  migrations.AddConstraint(model_name="finishedgoodstransferitem",constraint=models.CheckConstraint(condition=models.Q(received_quantity__lte=models.F("dispatched_quantity")-models.F("damaged_quantity")),name="fg_receipt_within_dispatch")),
 ]
