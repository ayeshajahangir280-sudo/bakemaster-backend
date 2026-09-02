from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission,HasLocationAccess
from .models import SalesInvoice,SalesReturn
from .serializers import SalesInvoiceSerializer,SalesReturnSerializer
from .services import post_sale,cancel_sale,post_return,cancel_return
from rest_framework.decorators import action
from rest_framework.response import Response
from common.idempotency import idempotent_action
from apps.inventory.document_services import generated_number
class SalesInvoiceViewSet(AuditedModelViewSet):
 serializer_class=SalesInvoiceSerializer;permission_classes=[HasModulePermission,HasLocationAccess];module_name="sales"
 def get_queryset(self):
  q=SalesInvoice.objects.prefetch_related("items").order_by("-invoice_date");u=self.request.user
  if getattr(self,"swagger_fake_view",False):return q.none()
  if not getattr(u,"is_authenticated",False):return q.none()
  return q if u.role=="ADMINISTRATOR" or u.can_access_all_locations or not u.assigned_location_id else q.filter(sales_location=u.assigned_location)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def post(self,request,pk=None):return Response({"success":True,"data":self.get_serializer(post_sale(pk,request.user)).data})
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):return Response({"success":True,"data":self.get_serializer(cancel_sale(pk,request.user,request.data.get("reason",""))).data})
class SalesReturnViewSet(AuditedModelViewSet):
 serializer_class=SalesReturnSerializer;permission_classes=[HasModulePermission,HasLocationAccess];module_name="sales_returns"
 def get_queryset(self):
  q=SalesReturn.objects.prefetch_related("items").order_by("-return_date");u=self.request.user
  if getattr(self,"swagger_fake_view",False):return q.none()
  if not getattr(u,"is_authenticated",False):return q.none()
  return q if u.role=="ADMINISTRATOR" or u.can_access_all_locations or not u.assigned_location_id else q.filter(return_location=u.assigned_location)
 def perform_create(self,serializer):serializer.save(return_number=generated_number("SRT"),created_by=self.request.user,updated_by=self.request.user)
 @action(detail=True,methods=["post"])
 def submit(self,request,pk=None):
  obj=self.get_object()
  if obj.status!="DRAFT":return Response({"detail":"Only draft returns can be submitted."},status=400)
  obj.status="SUBMITTED";obj.save(update_fields=["status"]);return Response(self.get_serializer(obj).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def post(self,request,pk=None):return Response(self.get_serializer(post_return(pk,request.user)).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):return Response(self.get_serializer(cancel_return(pk,request.user,request.data.get("reason",""))).data)
 def perform_update(self,serializer):
  if serializer.instance.status in {"POSTED","CANCELLED"}:raise __import__("rest_framework.exceptions",fromlist=["ValidationError"]).ValidationError("Posted returns are immutable.")
  super().perform_update(serializer)
