from django.db import models
from common.models import UUIDModel
class AuditLog(UUIDModel):
 user=models.ForeignKey("accounts.User",null=True,on_delete=models.SET_NULL);action=models.CharField(max_length=40);module=models.CharField(max_length=60);record_type=models.CharField(max_length=80);record_id=models.UUIDField(null=True);record_number=models.CharField(max_length=80,blank=True);description=models.TextField();previous_values=models.JSONField(default=dict,blank=True);new_values=models.JSONField(default=dict,blank=True);ip_address=models.GenericIPAddressField(null=True);created_at=models.DateTimeField(auto_now_add=True)
 class Meta:ordering=["-created_at"]
