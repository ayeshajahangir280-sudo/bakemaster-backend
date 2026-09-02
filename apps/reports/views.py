import csv
from decimal import Decimal

from django.db.models import Count,F,Q,Sum,Value
from django.db.models.functions import Coalesce,TruncDay,TruncMonth
from django.conf import settings
from django.http import FileResponse,StreamingHttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiTypes,extend_schema,inline_serializer
from rest_framework import serializers

from apps.accounts.permissions import HasModulePermission
from apps.audit.models import AuditLog
from apps.inventory.models import InventoryBalance,StockAdjustment,StockTransaction,WastageDocument
from apps.inventory.posting import reconciliation_discrepancies
from apps.master_data.models import Customer,RawMaterial,Supplier
from apps.payments.models import CustomerPayment,SupplierPayment
from apps.production.models import ProductionBatch,ProductionConsumption
from apps.purchasing.models import PurchaseInvoice,PurchaseInvoiceItem,SupplierLedger
from apps.sales.models import CustomerLedger,SalesInvoice,SalesInvoiceItem,SalesReturn
from common.pagination import StandardPagination
from .models import ReportExportJob


def _date_filters(request,field):
    result={}
    if request.query_params.get("date_from"):result[f"{field}__gte"]=request.query_params["date_from"]
    if request.query_params.get("date_to"):result[f"{field}__lte"]=request.query_params["date_to"]
    return result

def _location_id(request):
    user=request.user;requested=request.query_params.get("location")
    if user.role=="ADMINISTRATOR" or user.can_access_all_locations:return requested
    if user.assigned_location_id:
        if requested and str(user.assigned_location_id)!=requested:raise ValidationError("You do not have access to the requested location.")
        return str(user.assigned_location_id)
    return requested

def _materialize(request,rows):
    if getattr(request,"streaming_export",False):
        return rows.iterator(chunk_size=1000) if hasattr(rows,"iterator") else rows
    return list(rows)

class Echo:
    def write(self,value):return value

class ReportView(APIView):
    permission_classes=[HasModulePermission];module_name="reports";report_name=None
    def rows(self,request):raise NotImplementedError
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self,request):
        if request.query_params.get("export")=="csv":request.streaming_export=True
        rows=self.rows(request)
        if request.query_params.get("export")=="csv":
            iterator=iter(rows);first=next(iterator,None);columns=list(first.keys()) if first else []
            writer=csv.DictWriter(Echo(),fieldnames=columns)
            def stream():
                yield writer.writeheader()
                from .exports import safe_cell
                if first:yield writer.writerow({key:safe_cell(value) for key,value in first.items()})
                for row in iterator:yield writer.writerow({key:safe_cell(value) for key,value in row.items()})
            response=StreamingHttpResponse(stream(),content_type="text/csv");response["Content-Disposition"]=f'attachment; filename="{self.report_name}.csv"';return response
        paginator=StandardPagination();page=paginator.paginate_queryset(rows,request,view=self)
        return paginator.get_paginated_response(page)

class InventoryReport(ReportView):
    def rows(self,request):
        qs=InventoryBalance.objects.select_related("raw_material","finished_product","location").order_by("location__name","raw_material__name","finished_product__name")
        location=_location_id(request)
        if location:qs=qs.filter(location_id=location)
        if self.report_name=="raw-material-stock":qs=qs.filter(raw_material__isnull=False)
        elif self.report_name=="finished-goods-stock":qs=qs.filter(finished_product__isnull=False)
        elif self.report_name=="production-stock":qs=qs.filter(location__location_type="PRODUCTION")
        return _materialize(request,({"item_type":"RM" if row.raw_material_id else "FG","item_id":row.raw_material_id or row.finished_product_id,"item":(row.raw_material or row.finished_product).name,"location_id":row.location_id,"location":row.location.name,"quantity":row.current_quantity,"average_cost":row.average_unit_cost,"inventory_value":row.inventory_value,"revision":row.revision} for row in qs.iterator()))

class StockLedgerReport(ReportView):
    report_name="stock-ledger"
    def rows(self,request):
        qs=StockTransaction.objects.select_related("raw_material","finished_product","source_location","destination_location","unit").filter(**_date_filters(request,"transaction_date")).order_by("-transaction_date","-created_at")
        location=_location_id(request)
        if location:qs=qs.filter(Q(source_location_id=location)|Q(destination_location_id=location))
        for field in ("transaction_type","raw_material","finished_product"):
            if request.query_params.get(field):qs=qs.filter(**{field:request.query_params[field]})
        return _materialize(request,({"number":x.transaction_number,"date":x.transaction_date,"type":x.transaction_type,"reference_type":x.reference_type,"reference_id":x.reference_id,"item_type":"RM" if x.raw_material_id else "FG","item_id":x.raw_material_id or x.finished_product_id,"item":(x.raw_material or x.finished_product).name,"source":x.source_location.name if x.source_location else "","destination":x.destination_location.name if x.destination_location else "","quantity_in":x.quantity_in,"quantity_out":x.quantity_out,"unit":x.unit.code,"unit_cost":x.unit_cost,"total_value":x.total_value,"is_reversal":x.is_reversal} for x in qs.iterator()))

class DocumentReport(ReportView):
    def rows(self,request):
        model=WastageDocument if self.report_name=="wastage" else StockAdjustment
        date_field="wastage_date" if model is WastageDocument else "adjustment_date"
        qs=model.objects.select_related("raw_material","finished_product","location","unit").filter(**_date_filters(request,date_field)).order_by(f"-{date_field}","-created_at")
        location=_location_id(request)
        if location:qs=qs.filter(location_id=location)
        if request.query_params.get("status"):qs=qs.filter(status=request.query_params["status"])
        return _materialize(request,({"number":getattr(x,"document_number",None) or x.adjustment_number,"date":getattr(x,date_field),"item_type":"RM" if x.raw_material_id else "FG","item_id":x.raw_material_id or x.finished_product_id,"item":(x.raw_material or x.finished_product).name,"location":x.location.name,"quantity":x.quantity,"direction":getattr(x,"direction","OUT"),"unit":x.unit.code,"unit_cost":x.unit_cost,"total_value":x.total_value,"reason":x.reason,"status":x.status} for x in qs.iterator()))

class PurchaseReport(ReportView):
    def rows(self,request):
        if self.report_name=="supplier-ledger":
            qs=SupplierLedger.objects.select_related("supplier").filter(**_date_filters(request,"transaction_date")).order_by("-transaction_date","-created_at")
            if request.query_params.get("supplier"):qs=qs.filter(supplier_id=request.query_params["supplier"])
            return _materialize(request,qs.values("transaction_date","supplier_id","supplier__name","reference_type","reference_id","debit","credit"))
        if self.report_name=="supplier-outstanding":
            qs=Supplier.objects.annotate(invoice_total=Coalesce(Sum("purchaseinvoice__grand_total",filter=Q(purchaseinvoice__status__in=["POSTED","PARTIALLY_PAID","PAID","OVERDUE"])),Value(Decimal("0"))),payment_total=Coalesce(Sum("supplierpayment__amount",filter=Q(supplierpayment__status="POSTED")),Value(Decimal("0"))))
            return _materialize(request,({"supplier_id":x.id,"supplier":x.name,"opening_balance":x.opening_balance,"invoice_total":x.invoice_total,"payment_total":x.payment_total,"outstanding":x.opening_balance+x.invoice_total-x.payment_total} for x in qs.iterator()))
        if self.report_name=="purchases-by-item":
            qs=PurchaseInvoiceItem.objects.filter(purchase_invoice__status__in=["POSTED","PARTIALLY_PAID","PAID","OVERDUE"],**_date_filters(request,"purchase_invoice__invoice_date"))
            if request.query_params.get("raw_material"):qs=qs.filter(raw_material_id=request.query_params["raw_material"])
            return _materialize(request,qs.values("raw_material_id","raw_material__name").annotate(quantity=Sum("quantity"),total=Sum("line_total")).order_by("raw_material__name"))
        qs=PurchaseInvoice.objects.select_related("supplier","warehouse").filter(**_date_filters(request,"invoice_date")).order_by("-invoice_date")
        location=_location_id(request)
        if location:qs=qs.filter(warehouse_id=location)
        if request.query_params.get("supplier"):qs=qs.filter(supplier_id=request.query_params["supplier"])
        return _materialize(request,qs.values("id","invoice_number","invoice_date","due_date","supplier_id","supplier__name","warehouse_id","warehouse__name","status","grand_total","paid_amount","outstanding_amount"))

class ProductionReport(ReportView):
    def rows(self,request):
        if self.report_name=="material-consumption":
            qs=ProductionConsumption.objects.select_related("production_batch","raw_material").filter(**_date_filters(request,"production_batch__manufacturing_date"))
            return _materialize(request,qs.values("production_batch_id","production_batch__production_number","raw_material_id","raw_material__name","standard_required_quantity","actual_consumed_quantity","variance_quantity","unit_cost","total_cost"))
        qs=ProductionBatch.objects.select_related("finished_product","production_location","finished_goods_destination").filter(**_date_filters(request,"manufacturing_date")).order_by("-manufacturing_date")
        location=_location_id(request)
        if location:qs=qs.filter(Q(production_location_id=location)|Q(finished_goods_destination_id=location))
        return _materialize(request,qs.values("id","production_number","manufacturing_date","finished_product_id","finished_product__name","production_location_id","finished_goods_destination_id","status","planned_quantity","actual_produced_quantity","material_cost","additional_cost","total_production_cost","cost_per_unit"))

class SalesReport(ReportView):
    def rows(self,request):
        active=["POSTED","PARTIALLY_PAID","PAID","OVERDUE"]
        if self.report_name=="customer-ledger":
            qs=CustomerLedger.objects.select_related("customer").filter(**_date_filters(request,"transaction_date")).order_by("-transaction_date","-created_at")
            if request.query_params.get("customer"):qs=qs.filter(customer_id=request.query_params["customer"])
            return _materialize(request,qs.values("transaction_date","customer_id","customer__name","reference_type","reference_id","debit","credit"))
        if self.report_name=="customer-outstanding":
            qs=Customer.objects.annotate(invoice_total=Coalesce(Sum("salesinvoice__grand_total",filter=Q(salesinvoice__status__in=active)),Value(Decimal("0"))),payment_total=Coalesce(Sum("customerpayment__amount",filter=Q(customerpayment__status="POSTED")),Value(Decimal("0"))),return_total=Coalesce(Sum("salesreturn__credit_total",filter=Q(salesreturn__status="POSTED")),Value(Decimal("0"))))
            return _materialize(request,({"customer_id":x.id,"customer":x.name,"opening_balance":x.opening_balance,"invoice_total":x.invoice_total,"payment_total":x.payment_total,"return_total":x.return_total,"outstanding":x.opening_balance+x.invoice_total-x.payment_total-x.return_total} for x in qs.iterator()))
        if self.report_name in {"sales-by-product","sales-by-customer","sales-by-branch","daily-sales","monthly-sales"}:
            qs=SalesInvoiceItem.objects.filter(sales_invoice__status__in=active,**_date_filters(request,"sales_invoice__invoice_date"))
            location=_location_id(request)
            if location:qs=qs.filter(sales_invoice__sales_location_id=location)
            if request.query_params.get("finished_product"):qs=qs.filter(finished_product_id=request.query_params["finished_product"])
            if request.query_params.get("customer"):qs=qs.filter(sales_invoice__customer_id=request.query_params["customer"])
            dimensions={"sales-by-product":["finished_product_id","finished_product__name"],"sales-by-customer":["sales_invoice__customer_id","sales_invoice__customer__name"],"sales-by-branch":["sales_invoice__sales_location_id","sales_invoice__sales_location__name"]}
            if self.report_name=="daily-sales":return _materialize(request,qs.annotate(period=TruncDay("sales_invoice__invoice_date")).values("period").annotate(quantity=Sum("quantity"),sales=Sum("line_total"),cost=Sum("cost_total"),gross_profit=Sum("gross_profit")).order_by("period"))
            if self.report_name=="monthly-sales":return _materialize(request,qs.annotate(period=TruncMonth("sales_invoice__invoice_date")).values("period").annotate(quantity=Sum("quantity"),sales=Sum("line_total"),cost=Sum("cost_total"),gross_profit=Sum("gross_profit")).order_by("period"))
            return _materialize(request,qs.values(*dimensions[self.report_name]).annotate(quantity=Sum("quantity"),sales=Sum("line_total"),cost=Sum("cost_total"),gross_profit=Sum("gross_profit")).order_by("-sales"))
        qs=SalesInvoice.objects.select_related("customer","sales_location").filter(**_date_filters(request,"invoice_date")).order_by("-invoice_date")
        location=_location_id(request)
        if location:qs=qs.filter(sales_location_id=location)
        if request.query_params.get("customer"):qs=qs.filter(customer_id=request.query_params["customer"])
        return _materialize(request,qs.values("id","invoice_number","invoice_date","due_date","customer_id","customer__name","sales_location_id","sales_location__name","status","grand_total","paid_amount","outstanding_amount","cost_of_goods_sold","gross_profit","gross_margin_percentage"))

class ReturnsPaymentsReport(ReportView):
    def rows(self,request):
        if self.report_name in {"sales-returns","return-analysis","customer-return-history"}:
            qs=SalesReturn.objects.select_related("customer","original_sales_invoice","return_location").filter(**_date_filters(request,"return_date")).order_by("-return_date")
            if request.query_params.get("customer"):qs=qs.filter(customer_id=request.query_params["customer"])
            return _materialize(request,qs.values("id","return_number","return_date","customer_id","customer__name","original_sales_invoice_id","return_location_id","reason","status","credit_total"))
        model=CustomerPayment if self.report_name=="customer-payments" else SupplierPayment
        party="customer" if model is CustomerPayment else "supplier"
        qs=model.objects.select_related(party,"payment_method").prefetch_related("allocations").filter(**_date_filters(request,"payment_date")).order_by("-payment_date")
        return _materialize(request,({"id":x.id,"number":x.payment_number,"date":x.payment_date,"party_id":getattr(x,f"{party}_id"),"party":getattr(x,party).name,"method":x.payment_method.name,"amount":x.amount,"allocated":sum((a.amount for a in x.allocations.all()),Decimal("0")),"status":x.status,"reference":x.reference_number} for x in qs.iterator()))

class ReconciliationReport(ReportView):
    report_name="reconciliation"
    def rows(self,request):return reconciliation_discrepancies()

class DashboardView(APIView):
    permission_classes=[HasModulePermission];module_name="dashboard"
    @extend_schema(operation_id="dashboard_retrieve",responses=OpenApiTypes.OBJECT)
    def get(self,request):
        today=timezone.localdate();location=_location_id(request);active=["POSTED","PARTIALLY_PAID","PAID","OVERDUE"]
        purchases=PurchaseInvoice.objects.filter(status__in=active);sales=SalesInvoice.objects.filter(status__in=active);production=ProductionBatch.objects.filter(status__in=["COMPLETED","POSTED"]);balances=InventoryBalance.objects.all()
        if location:purchases=purchases.filter(warehouse_id=location);sales=sales.filter(sales_location_id=location);production=production.filter(Q(production_location_id=location)|Q(finished_goods_destination_id=location));balances=balances.filter(location_id=location)
        top_products=list(SalesInvoiceItem.objects.filter(sales_invoice__in=sales).values("finished_product_id","finished_product__name").annotate(quantity=Sum("quantity"),sales=Sum("line_total")).order_by("-quantity")[:10])
        top_customers=list(sales.values("customer_id","customer__name").annotate(sales=Sum("grand_total")).order_by("-sales")[:10])
        pending=WastageDocument.objects.filter(status__in=["SUBMITTED","APPROVED"]).count()+StockAdjustment.objects.filter(status__in=["SUBMITTED","APPROVED"]).count()
        sales_items=SalesInvoiceItem.objects.filter(sales_invoice__in=sales)
        low_fg=list(balances.filter(finished_product__isnull=False,current_quantity__lte=F("finished_product__minimum_stock")).values("finished_product_id","finished_product__name","location_id","location__name","current_quantity","finished_product__minimum_stock")[:50])
        data={"total_purchases":purchases.aggregate(total=Coalesce(Sum("grand_total"),Value(Decimal("0"))))["total"],"production_today":production.filter(manufacturing_date=today).aggregate(total=Coalesce(Sum("actual_produced_quantity"),Value(Decimal("0"))))["total"],"finished_goods_quantity":balances.filter(finished_product__isnull=False).aggregate(total=Coalesce(Sum("current_quantity"),Value(Decimal("0"))))["total"],"daily_sales":sales.filter(invoice_date=today).aggregate(total=Coalesce(Sum("grand_total"),Value(Decimal("0"))))["total"],"monthly_sales":sales.filter(invoice_date__year=today.year,invoice_date__month=today.month).aggregate(total=Coalesce(Sum("grand_total"),Value(Decimal("0"))))["total"],"inventory_value":balances.aggregate(total=Coalesce(Sum("inventory_value"),Value(Decimal("0"))))["total"],"receivables":sales.aggregate(total=Coalesce(Sum("outstanding_amount"),Value(Decimal("0"))))["total"],"payables":purchases.aggregate(total=Coalesce(Sum("outstanding_amount"),Value(Decimal("0"))))["total"],"low_stock_raw_materials":balances.filter(raw_material__isnull=False,current_quantity__lte=F("raw_material__reorder_level")).count(),"low_stock_finished_goods":len(low_fg),"pending_approvals":pending,"reconciliation_discrepancies":len(reconciliation_discrepancies()),"top_products":top_products,"top_customers":top_customers,"low_stock_finished_goods_details":low_fg,"daily_trend":list(sales.values("invoice_date").annotate(sales=Sum("grand_total")).order_by("invoice_date")),"monthly_trend":list(sales.annotate(period=TruncMonth("invoice_date")).values("period").annotate(sales=Sum("grand_total")).order_by("period")),"branch_comparison":list(sales.values("sales_location_id","sales_location__name").annotate(sales=Sum("grand_total")).order_by("-sales")),"gross_profit":sales.aggregate(total=Coalesce(Sum("gross_profit"),Value(Decimal("0"))))["total"],"gross_margin":sales_items.aggregate(sales=Coalesce(Sum("line_total"),Value(Decimal("0"))),profit=Coalesce(Sum("gross_profit"),Value(Decimal("0")))) ,"returns_total":SalesReturn.objects.filter(status="POSTED",**({"return_location_id":location} if location else {})).aggregate(total=Coalesce(Sum("credit_total"),Value(Decimal("0"))))["total"],"wastage_total":WastageDocument.objects.filter(status="POSTED",**({"location_id":location} if location else {})).aggregate(total=Coalesce(Sum("total_value"),Value(Decimal("0"))))["total"],"adjustment_total":StockAdjustment.objects.filter(status="POSTED",**({"location_id":location} if location else {})).aggregate(total=Coalesce(Sum("total_value"),Value(Decimal("0"))))["total"]}
        gross=data.pop("gross_margin");data["gross_margin_percentage"]=(gross["profit"]/gross["sales"]*Decimal("100")) if gross["sales"] else Decimal("0")
        return Response(data)

class ReportExportJobView(APIView):
    permission_classes=[HasModulePermission];module_name="reports"
    def get(self,request,pk=None):
        qs=ReportExportJob.objects.filter(requested_by=request.user)
        if pk:
            job=qs.get(pk=pk);return Response(self.serialize(job))
        return Response([self.serialize(job) for job in qs[:100]])
    def post(self,request,pk=None):
        from .exports import REPORTS,build_xlsx,safe_filename
        if pk:
            job=ReportExportJob.objects.filter(requested_by=request.user).get(pk=pk)
            if job.status!="FAILED":return Response({"detail":"Only failed exports can be retried."},status=409)
            job.status="PENDING";job.error="";job.save(update_fields=["status","error"]);return Response(self.serialize(job))
        report=str(request.data.get("report_name","")).strip();output=str(request.data.get("format","XLSX")).upper()
        if report not in REPORTS:return Response({"detail":"Unsupported report."},status=400)
        if output not in {"CSV","XLSX"}:return Response({"detail":"Format must be CSV or XLSX."},status=400)
        filters={str(k):str(v) for k,v in dict(request.data.get("filters") or {}).items() if v not in (None,"")}
        _location_id(SimpleRequest(request.user,filters))
        report_view=REPORTS[report](report_name=report)
        export_request=SimpleRequest(request.user,filters)
        if output=="CSV":
            rows=iter(report_view.rows(export_request));first=next(rows,None);columns=list(first.keys()) if first else []
            writer=csv.DictWriter(Echo(),fieldnames=columns)
            from .exports import safe_cell
            def stream():
                yield writer.writeheader()
                if first:yield writer.writerow({key:safe_cell(value) for key,value in first.items()})
                for row in rows:yield writer.writerow({key:safe_cell(value) for key,value in row.items()})
            response=StreamingHttpResponse(stream(),content_type="text/csv")
            response["Content-Disposition"]=f'attachment; filename="{safe_filename(report,"csv")}"'
        else:
            try:target=build_xlsx(report_view.rows(export_request),settings.REPORT_XLSX_MAX_ROWS)
            except OverflowError:
                return Response({"detail":f"Excel exports are limited to {settings.REPORT_XLSX_MAX_ROWS:,} rows. Use CSV for larger exports."},status=400)
            response=FileResponse(target,as_attachment=True,filename=safe_filename(report,"xlsx"),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        AuditLog.objects.create(user=request.user,action="Export",module="reports",record_type="Report",record_number=report,description=f"Exported {report} as {output}",new_values={"filters":filters,"format":output})
        return response
    @staticmethod
    def serialize(job):return {"id":job.id,"report_name":job.report_name,"format":job.output_format,"filters":job.filters,"status":job.status,"attempts":job.attempts,"error":job.error,"created_at":job.created_at,"completed_at":job.completed_at,"expires_at":job.expires_at,"download_available":bool(job.file and job.status=="COMPLETED")}

class SimpleRequest:
    def __init__(self,user,query_params):self.user=user;self.query_params=query_params;self.streaming_export=True

class ReportExportDownloadView(APIView):
    permission_classes=[HasModulePermission];module_name="reports"
    @extend_schema(operation_id="report_export_download",responses={(200,"application/octet-stream"):OpenApiTypes.BINARY})
    def get(self,request,pk):
        job=ReportExportJob.objects.filter(requested_by=request.user).get(pk=pk)
        if job.status!="COMPLETED" or not job.file:return Response({"detail":"Export is not available."},status=409)
        if job.expires_at<=timezone.now():return Response({"detail":"Export has expired."},status=410)
        return FileResponse(job.file.open("rb"),as_attachment=True,filename=job.file.name.rsplit("/",1)[-1])

class ReportExportCollectionView(ReportExportJobView):
    @extend_schema(operation_id="report_export_list",responses=OpenApiTypes.OBJECT)
    def get(self,request):return super().get(request)
    @extend_schema(operation_id="report_export_create",request=inline_serializer("ReportExportCreateRequest",fields={"report_name":serializers.CharField(),"format":serializers.ChoiceField(choices=("CSV","XLSX")),"filters":serializers.JSONField(required=False)}),responses={(200,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):OpenApiTypes.BINARY,(200,"text/csv"):OpenApiTypes.BINARY})
    def post(self,request):return super().post(request)

class ReportExportDetailView(ReportExportJobView):
    @extend_schema(operation_id="report_export_retrieve",responses=OpenApiTypes.OBJECT)
    def get(self,request,pk):return super().get(request,pk)
    @extend_schema(operation_id="report_export_retry",request=None,responses=OpenApiTypes.OBJECT)
    def post(self,request,pk):return super().post(request,pk)
