import csv,json
from decimal import Decimal
from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from django.db.models import Count,Sum
from apps.payments.models import CustomerPayment,CustomerPaymentAllocation,SupplierPayment,SupplierPaymentAllocation

class Command(BaseCommand):
    help="Read-only preflight audit for payment constraint and allocation migration safety."
    def add_arguments(self,parser):parser.add_argument("--format",choices=("human","json","csv"),default="human")
    def handle(self,*args,**options):
        findings=[]
        def add(code,severity,kind,record_id,number,message):findings.append({"code":code,"severity":severity,"kind":kind,"record_id":str(record_id or ""),"document_number":str(number or ""),"message":message})
        valid={"DRAFT","POSTED","CANCELLED"}
        configurations=((CustomerPayment,CustomerPaymentAllocation,"customer","customer_id"),(SupplierPayment,SupplierPaymentAllocation,"supplier","supplier_id"))
        for Payment,Allocation,party_name,party_field in configurations:
            kind=Payment.__name__
            for payment in Payment.objects.filter(amount__lte=0).only("id","payment_number","amount"):add("NON_POSITIVE_PAYMENT","blocking",kind,payment.id,payment.payment_number,f"Payment amount is {payment.amount}; it must be positive.")
            for payment in Payment.objects.exclude(status__in=valid).only("id","payment_number","status"):add("INVALID_STATUS","blocking",kind,payment.id,payment.payment_number,f"Unsupported payment status: {payment.status}.")
            for allocation in Allocation.objects.filter(amount__lte=0).select_related("payment"):add("NON_POSITIVE_ALLOCATION","blocking",kind,allocation.id,allocation.payment.payment_number,f"Allocation amount is {allocation.amount}; it must be positive.")
            duplicates=Allocation.objects.values("payment_id","invoice_id").annotate(count=Count("id")).filter(count__gt=1)
            for duplicate in duplicates:
                payment=Payment.objects.filter(pk=duplicate["payment_id"]).first();add("DUPLICATE_ALLOCATION","blocking",kind,duplicate["payment_id"],getattr(payment,"payment_number",""),f"Invoice {duplicate['invoice_id']} is allocated {duplicate['count']} times by this payment.")
            totals={row["payment_id"]:row["total"] or Decimal("0") for row in Allocation.objects.values("payment_id").annotate(total=Sum("amount"))}
            for payment in Payment.objects.all().iterator():
                allocated=totals.get(payment.id,Decimal("0"))
                if allocated>payment.amount:add("PAYMENT_OVERALLOCATED","blocking",kind,payment.id,payment.payment_number,f"Allocated {allocated} exceeds payment amount {payment.amount}.")
                if allocated==0:add("NO_ALLOCATIONS","warning",kind,payment.id,payment.payment_number,"Payment has no invoice allocations.")
            for allocation in Allocation.objects.select_related("payment","invoice").iterator():
                payment=allocation.payment;invoice=allocation.invoice
                if getattr(payment,party_field)!=getattr(invoice,party_field):add("PARTY_MISMATCH","blocking",kind,allocation.id,payment.payment_number,f"Allocated invoice {invoice.invoice_number} belongs to another {party_name}.")
                if invoice.status in {"DRAFT","CANCELLED"}:add("INVOICE_NOT_PAYABLE","blocking",kind,allocation.id,payment.payment_number,f"Invoice {invoice.invoice_number} has status {invoice.status}.")
                # Draft payments have not reduced outstanding yet. Posted payments
                # may legitimately equal outstanding plus their applied allocation.
                available=invoice.outstanding_amount+(allocation.amount if payment.status=="POSTED" else Decimal("0"))
                if allocation.amount>available:add("ALLOCATION_EXCEEDS_OUTSTANDING","blocking",kind,allocation.id,payment.payment_number,f"Allocation {allocation.amount} exceeds available invoice outstanding {available} for {invoice.invoice_number}.")
        # LEFT JOIN checks remain useful before constraints are installed or
        # when a legacy database previously had constraint checks disabled.
        orphan_checks=(
            ("payments_customerpayment","master_data_customer","customer_id","MISSING_PARTY","CustomerPayment"),
            ("payments_supplierpayment","master_data_supplier","supplier_id","MISSING_PARTY","SupplierPayment"),
            ("payments_customerpayment","master_data_paymentmethod","payment_method_id","MISSING_PAYMENT_METHOD","CustomerPayment"),
            ("payments_supplierpayment","master_data_paymentmethod","payment_method_id","MISSING_PAYMENT_METHOD","SupplierPayment"),
            ("payments_customerpaymentallocation","payments_customerpayment","payment_id","ORPHANED_PAYMENT","CustomerPaymentAllocation"),
            ("payments_supplierpaymentallocation","payments_supplierpayment","payment_id","ORPHANED_PAYMENT","SupplierPaymentAllocation"),
            ("payments_customerpaymentallocation","sales_salesinvoice","invoice_id","ORPHANED_INVOICE","CustomerPaymentAllocation"),
            ("payments_supplierpaymentallocation","purchasing_purchaseinvoice","invoice_id","ORPHANED_INVOICE","SupplierPaymentAllocation"),
        )
        quote=connection.ops.quote_name
        with connection.cursor() as cursor:
            for source,target,column,code,kind in orphan_checks:
                cursor.execute(f"SELECT s.id FROM {quote(source)} s LEFT JOIN {quote(target)} t ON s.{quote(column)}=t.id WHERE s.{quote(column)} IS NULL OR t.id IS NULL")
                for (record_id,) in cursor.fetchall():add(code,"blocking",kind,record_id,"",f"Required reference {column} is missing or orphaned.")
        blocking=sum(item["severity"]=="blocking" for item in findings);warnings=len(findings)-blocking
        output=options["format"]
        if output=="json":self.stdout.write(json.dumps({"blocking":blocking,"warnings":warnings,"findings":findings},indent=2))
        elif output=="csv":
            writer=csv.DictWriter(self.stdout,fieldnames=("code","severity","kind","record_id","document_number","message"));writer.writeheader();writer.writerows(findings)
        else:
            for item in findings:self.stdout.write(f"[{item['severity'].upper()}] {item['code']} {item['kind']} {item['document_number']} ({item['record_id']}): {item['message']}")
            self.stdout.write(f"Payment migration preflight: {blocking} blocking issue(s), {warnings} warning(s).")
        if blocking:raise CommandError("Payment migration preflight failed. Correct blocking records through approved methods and run it again.")
