import csv, os, re, tempfile
from itertools import chain,islice
from decimal import Decimal
from uuid import UUID
from types import SimpleNamespace

from django.core.files import File
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook

from apps.audit.models import AuditLog
from .models import ReportExportJob
from .views import DocumentReport,InventoryReport,ProductionReport,PurchaseReport,ReconciliationReport,ReturnsPaymentsReport,SalesReport,StockLedgerReport

REPORTS={}
for names,view in [(("raw-material-stock","production-stock","finished-goods-stock","stock-by-location","inventory-valuation"),InventoryReport),(("stock-ledger","stock-movement","item-movement-history"),StockLedgerReport),(("wastage","adjustments"),DocumentReport),(("purchase-register","supplier-ledger","supplier-outstanding","purchases-by-item"),PurchaseReport),(("production-register","material-consumption","production-cost","production-efficiency"),ProductionReport),(("sales-register","customer-ledger","customer-outstanding","sales-by-product","sales-by-customer","sales-by-branch","daily-sales","monthly-sales","gross-profit"),SalesReport),(("sales-returns","return-analysis","customer-return-history","customer-payments","supplier-payments"),ReturnsPaymentsReport),(("reconciliation",),ReconciliationReport)]:
 for name in names:REPORTS[name]=view

FORMULA_PREFIXES=("=","+","-","@")

def safe_cell(value):
 if isinstance(value,str) and value.lstrip().startswith(FORMULA_PREFIXES):return "'"+value
 if isinstance(value,(UUID,Decimal)):return str(value)
 return value

def safe_filename(report_name,suffix):
 name=re.sub(r"[^A-Za-z0-9._-]+","-",report_name).strip("-.") or "report"
 return f"{name}-{timezone.now():%Y%m%d-%H%M%S}.{suffix}"

def prepare_rows(rows,max_rows=None):
 iterator=iter(rows);first=next(iterator,None)
 if first is None:return [],iter(())
 columns=list(first.keys())
 def sanitized():
  for index,row in enumerate(chain((first,),iterator),start=1):
   if max_rows is not None and index>max_rows:raise OverflowError
   yield [safe_cell(row.get(column)) for column in columns]
 return columns,sanitized()

def build_xlsx(rows,max_rows=None):
 if max_rows is not None:
  buffered=list(islice(iter(rows),max_rows+1))
  if len(buffered)>max_rows:raise OverflowError
  rows=buffered
 target=tempfile.SpooledTemporaryFile(max_size=settings.REPORT_EXPORT_SPOOL_MAX_BYTES,mode="w+b")
 book=Workbook(write_only=True);sheet=book.create_sheet("Report")
 columns,values=prepare_rows(rows);sheet.append(columns)
 for row in values:sheet.append(row)
 book.save(target);target.seek(0);return target

def report_rows(job):
 request=SimpleNamespace(user=job.requested_by,query_params=job.filters)
 view=REPORTS[job.report_name](report_name=job.report_name)
 return iter(view.rows(request))

def process_export(job_id):
 with transaction.atomic():
  job=ReportExportJob.objects.select_for_update().select_related("requested_by").get(pk=job_id)
  if job.status not in {"PENDING","FAILED"}:return job
  job.status="RUNNING";job.attempts+=1;job.started_at=timezone.now();job.error="";job.save(update_fields=["status","attempts","started_at","error"])
 path=None
 try:
  rows=report_rows(job);first=next(rows,None);columns=list(first.keys()) if first else []
  suffix=".xlsx" if job.output_format=="XLSX" else ".csv"
  fd,path=tempfile.mkstemp(suffix=suffix);os.close(fd)
  if job.output_format=="XLSX":
   target=build_xlsx(chain((first,),rows) if first else (),max_rows=None)
   with open(path,"wb") as output:
    while chunk:=target.read(1024*1024):output.write(chunk)
   target.close()
  else:
   with open(path,"w",newline="",encoding="utf-8-sig") as target:
    writer=csv.DictWriter(target,fieldnames=columns);writer.writeheader()
    if first:writer.writerow({key:safe_cell(value) for key,value in first.items()})
    for row in rows:writer.writerow({key:safe_cell(value) for key,value in row.items()})
  with open(path,"rb") as source:job.file.save(f"{job.report_name}-{job.id}{suffix}",File(source),save=False)
  job.status="COMPLETED";job.completed_at=timezone.now();job.save(update_fields=["file","status","completed_at"])
  AuditLog.objects.create(user=job.requested_by,action="Export",module="reports",record_type="ReportExportJob",record_id=job.id,record_number=str(job.id),description=f"Completed {job.report_name} {job.output_format} export",new_values={"filters":job.filters,"format":job.output_format})
 except Exception as exc:
  job.status="FAILED";job.error=str(exc)[:2000];job.completed_at=timezone.now();job.save(update_fields=["status","error","completed_at"]);raise
 finally:
  if path and os.path.exists(path):os.unlink(path)
 return job
