from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import CustomerPayment,SupplierPayment
from .serializers import CustomerPaymentSerializer,SupplierPaymentSerializer
from .services import cancel_payment,payment_number,post_payment
from common.idempotency import idempotent_action

class PaymentViewSet(ModelViewSet):
 permission_classes=[HasModulePermission];filterset_fields=["status","payment_date"]
 payment_class=None;prefix=None
 def get_queryset(self):return self.payment_class.objects.prefetch_related("allocations").order_by("-payment_date","-created_at")
 def perform_create(self,serializer):serializer.save(created_by=self.request.user,payment_number=payment_number(self.prefix))
 def perform_destroy(self,instance):
  if instance.status!="DRAFT":raise ValidationError("Posted or cancelled payments cannot be deleted.")
  instance.delete()
 @action(detail=True,methods=["post"])
 @idempotent_action
 def post(self,request,pk=None):return Response(self.get_serializer(post_payment(self.payment_class,pk,request.user)).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):
  reason=str(request.data.get("reason","")).strip()
  if not reason:raise ValidationError("Cancellation reason is required.")
  return Response(self.get_serializer(cancel_payment(self.payment_class,pk,request.user,reason)).data)

class CustomerPaymentViewSet(PaymentViewSet):
 serializer_class=CustomerPaymentSerializer;module_name="customer_payments";payment_class=CustomerPayment;prefix="CPY"
 def get_queryset(self):
  qs=super().get_queryset();u=self.request.user
  if getattr(self,"swagger_fake_view",False):return qs.none()
  if not getattr(u,"is_authenticated",False):return qs.none()
  if u.role!="ADMINISTRATOR" and not u.can_access_all_locations and u.assigned_location_id:qs=qs.filter(customer__assigned_location=u.assigned_location)
  return qs
class SupplierPaymentViewSet(PaymentViewSet):
 serializer_class=SupplierPaymentSerializer;module_name="supplier_payments";payment_class=SupplierPayment;prefix="SPY"
