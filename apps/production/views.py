from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import ProductionBatch
from .serializers import ProductionBatchSerializer
from .services import complete_production, reverse_production
from rest_framework.decorators import action
from rest_framework.response import Response
from common.idempotency import idempotent_action
class ProductionBatchViewSet(AuditedModelViewSet):
 queryset=ProductionBatch.objects.all();serializer_class=ProductionBatchSerializer;permission_classes=[HasModulePermission];module_name="production"
 @action(detail=True,methods=["post"])
 @idempotent_action
 def complete(self,request,pk=None):
  return Response({"success":True,"data":self.get_serializer(complete_production(pk,request.user,request.data.get("actual_quantity"))).data})
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):
  return Response({"success":True,"data":self.get_serializer(reverse_production(pk,request.user,request.data.get("reason",""))).data})
