from decimal import Decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import CustomerPayment,CustomerPaymentAllocation,SupplierPayment,SupplierPaymentAllocation

class AllocationSerializer(serializers.ModelSerializer):
 class Meta:fields=("id","invoice","amount");read_only_fields=("id",)

class CustomerPaymentAllocationSerializer(AllocationSerializer):
 class Meta(AllocationSerializer.Meta):model=CustomerPaymentAllocation
class SupplierPaymentAllocationSerializer(AllocationSerializer):
 class Meta(AllocationSerializer.Meta):model=SupplierPaymentAllocation

class PaymentSerializer(serializers.ModelSerializer):
 allocated_amount=serializers.SerializerMethodField();unallocated_amount=serializers.SerializerMethodField()
 @extend_schema_field(serializers.DecimalField(max_digits=18,decimal_places=2))
 def get_allocated_amount(self,obj)->Decimal:return sum((x.amount for x in obj.allocations.all()),Decimal("0"))
 @extend_schema_field(serializers.DecimalField(max_digits=18,decimal_places=2))
 def get_unallocated_amount(self,obj)->Decimal:return obj.amount-self.get_allocated_amount(obj)
 def validate(self,data):
  if self.instance and self.instance.status!="DRAFT":raise serializers.ValidationError("Posted or cancelled payments are immutable.")
  allocations=data.get("allocations",[]);total=sum((x["amount"] for x in allocations),Decimal("0"))
  if total>data.get("amount",getattr(self.instance,"amount",Decimal("0"))):raise serializers.ValidationError({"allocations":"Total allocations cannot exceed payment amount."})
  return data
 def create(self,validated):
  allocations=validated.pop("allocations",[]);payment=super().create(validated)
  for allocation in allocations:self.Meta.allocation_model.objects.create(payment=payment,**allocation)
  return payment
 def update(self,instance,validated):
  allocations=validated.pop("allocations",None);instance=super().update(instance,validated)
  if allocations is not None:
   instance.allocations.all().delete()
   for allocation in allocations:self.Meta.allocation_model.objects.create(payment=instance,**allocation)
  return instance

class CustomerPaymentSerializer(PaymentSerializer):
 allocations=CustomerPaymentAllocationSerializer(many=True)
 class Meta:model=CustomerPayment;allocation_model=CustomerPaymentAllocation;fields="__all__";read_only_fields=("payment_number","status","created_by","posted_by","posted_at","cancelled_by","cancelled_at","cancellation_reason")
class SupplierPaymentSerializer(PaymentSerializer):
 allocations=SupplierPaymentAllocationSerializer(many=True)
 class Meta:model=SupplierPayment;allocation_model=SupplierPaymentAllocation;fields="__all__";read_only_fields=("payment_number","status","created_by","posted_by","posted_at","cancelled_by","cancelled_at","cancellation_reason")
