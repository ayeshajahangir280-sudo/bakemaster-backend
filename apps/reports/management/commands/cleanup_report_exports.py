from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.reports.models import ReportExportJob

class Command(BaseCommand):
 help="Delete expired report files and mark their jobs expired."
 def handle(self,*args,**options):
  count=0
  for job in ReportExportJob.objects.filter(expires_at__lt=timezone.now()).exclude(status="EXPIRED"):
   if job.file:job.file.delete(save=False)
   job.status="EXPIRED";job.save(update_fields=["status"]);count+=1
  self.stdout.write(self.style.SUCCESS(f"Expired {count} report exports."))
