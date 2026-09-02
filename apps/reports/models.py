# Reports are read models built from transactional applications.
import uuid

from django.conf import settings
from django.db import models


class ReportExportJob(models.Model):
    FORMATS=(("CSV","CSV"),("XLSX","Excel"));STATUSES=(("PENDING","Pending"),("RUNNING","Running"),("COMPLETED","Completed"),("FAILED","Failed"),("EXPIRED","Expired"))
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="report_exports")
    report_name=models.CharField(max_length=80)
    output_format=models.CharField(max_length=8,choices=FORMATS)
    filters=models.JSONField(default=dict)
    status=models.CharField(max_length=12,choices=STATUSES,default="PENDING")
    attempts=models.PositiveSmallIntegerField(default=0)
    error=models.TextField(blank=True)
    file=models.FileField(upload_to="report-exports/%Y/%m/%d",blank=True)
    created_at=models.DateTimeField(auto_now_add=True);started_at=models.DateTimeField(null=True,blank=True);completed_at=models.DateTimeField(null=True,blank=True);expires_at=models.DateTimeField()
    class Meta:ordering=("-created_at",);indexes=[models.Index(fields=("status","created_at"),name="report_export_queue_idx"),models.Index(fields=("expires_at",),name="report_export_expiry_idx")]
