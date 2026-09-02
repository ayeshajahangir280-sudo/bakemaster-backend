from django.db import models
from common.models import TransactionalModel,UUIDModel
from django.db.models import Q
class CustomerPayment(TransactionalModel):
 payment_number=models.CharField(max_length=50,unique=True,editable=False);customer=models.ForeignKey("master_data.Customer",on_delete=models.PROTECT);payment_date=models.DateField();amount=models.DecimalField(max_digits=18,decimal_places=2);payment_method=models.ForeignKey("master_data.PaymentMethod",on_delete=models.PROTECT);reference_number=models.CharField(max_length=100,blank=True);notes=models.TextField(blank=True);status=models.CharField(max_length=20,choices=[("DRAFT","Draft"),("POSTED","Posted"),("CANCELLED","Cancelled")],default="DRAFT")
 class Meta:constraints=[models.CheckConstraint(condition=Q(amount__gt=0),name="customer_payment_positive_amount")];indexes=[models.Index(fields=["customer","payment_date","status"],name="cust_pay_party_date_idx")]
class CustomerPaymentAllocation(UUIDModel):
 payment=models.ForeignKey(CustomerPayment,on_delete=models.CASCADE,related_name="allocations");invoice=models.ForeignKey("sales.SalesInvoice",on_delete=models.PROTECT);amount=models.DecimalField(max_digits=18,decimal_places=2)
 class Meta:constraints=[models.CheckConstraint(condition=Q(amount__gt=0),name="customer_allocation_positive_amount"),models.UniqueConstraint(fields=["payment","invoice"],name="unique_customer_payment_invoice")];indexes=[models.Index(fields=["invoice","payment"],name="customer_alloc_invoice_idx")]
class SupplierPayment(TransactionalModel):
 payment_number=models.CharField(max_length=50,unique=True,editable=False);supplier=models.ForeignKey("master_data.Supplier",on_delete=models.PROTECT);payment_date=models.DateField();amount=models.DecimalField(max_digits=18,decimal_places=2);payment_method=models.ForeignKey("master_data.PaymentMethod",on_delete=models.PROTECT);reference_number=models.CharField(max_length=100,blank=True);notes=models.TextField(blank=True);status=models.CharField(max_length=20,choices=[("DRAFT","Draft"),("POSTED","Posted"),("CANCELLED","Cancelled")],default="DRAFT")
 class Meta:constraints=[models.CheckConstraint(condition=Q(amount__gt=0),name="supplier_payment_positive_amount")];indexes=[models.Index(fields=["supplier","payment_date","status"],name="supp_pay_party_date_idx")]
class SupplierPaymentAllocation(UUIDModel):
 payment=models.ForeignKey(SupplierPayment,on_delete=models.CASCADE,related_name="allocations");invoice=models.ForeignKey("purchasing.PurchaseInvoice",on_delete=models.PROTECT);amount=models.DecimalField(max_digits=18,decimal_places=2)
 class Meta:constraints=[models.CheckConstraint(condition=Q(amount__gt=0),name="supplier_allocation_positive_amount"),models.UniqueConstraint(fields=["payment","invoice"],name="unique_supplier_payment_invoice")];indexes=[models.Index(fields=["invoice","payment"],name="supplier_alloc_invoice_idx")]
