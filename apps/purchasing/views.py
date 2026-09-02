from rest_framework.decorators import action
from rest_framework.response import Response
from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission,HasLocationAccess
from .models import PurchaseInvoice
from .serializers import PurchaseSerializer
from .services import post_purchase,cancel_purchase
from common.idempotency import idempotent_action
class PurchaseViewSet(AuditedModelViewSet):
 serializer_class=PurchaseSerializer;permission_classes=[HasModulePermission,HasLocationAccess];module_name="purchasing";filterset_fields=["supplier","warehouse","status"]
 def get_queryset(self):
  q=PurchaseInvoice.objects.prefetch_related("items").order_by("-invoice_date");u=self.request.user
  if getattr(self,"swagger_fake_view",False):return q.none()
  if not getattr(u,"is_authenticated",False):return q.none()
  return q if u.role=="ADMINISTRATOR" or u.can_access_all_locations or not u.assigned_location_id else q.filter(warehouse=u.assigned_location)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def post(self,request,pk=None): return Response({"success":True,"message":"Purchase invoice posted successfully.","data":self.get_serializer(post_purchase(pk,request.user)).data})
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None): return Response({"success":True,"message":"Purchase invoice cancelled.","data":self.get_serializer(cancel_purchase(pk,request.user,request.data.get("reason",""))).data})
