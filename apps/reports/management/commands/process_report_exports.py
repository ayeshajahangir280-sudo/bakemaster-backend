import time
from django.core.management.base import BaseCommand
from apps.reports.exports import process_export
from apps.reports.models import ReportExportJob

class Command(BaseCommand):
 help="Process database-backed report exports in a separate worker."
 def add_arguments(self,parser):parser.add_argument("--once",action="store_true");parser.add_argument("--poll-seconds",type=float,default=2)
 def handle(self,*args,**options):
  while True:
   job=ReportExportJob.objects.filter(status="PENDING").order_by("created_at").first()
   if job:
    try:process_export(job.id)
    except Exception as exc:self.stderr.write(f"Export {job.id} failed: {exc}")
   elif options["once"]:return
   else:time.sleep(max(.2,options["poll_seconds"]))
   if options["once"]:return
