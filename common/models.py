import uuid
from django.conf import settings
from django.db import models
class UUIDModel(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    class Meta: abstract=True
class AuditedModel(UUIDModel):
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="created_%(class)ss")
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="updated_%(class)ss")
    class Meta: abstract=True
class TransactionalModel(AuditedModel):
    posted_at=models.DateTimeField(null=True,blank=True); posted_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="posted_%(class)ss")
    cancelled_at=models.DateTimeField(null=True,blank=True); cancelled_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="cancelled_%(class)ss"); cancellation_reason=models.TextField(blank=True)
    class Meta: abstract=True
