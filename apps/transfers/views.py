from rest_framework.decorators import action
from rest_framework.response import Response
from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import MaterialTransfer,FinishedGoodsTransfer
from .serializers import MaterialTransferSerializer,FinishedGoodsTransferSerializer
from .services import _transition,dispatch as dispatch_transfer,receive,cancel_transfer
from common.idempotency import idempotent_action
from apps.inventory.document_services import generated_number
from django.db.models import Q
class BaseTransferViewSet(AuditedModelViewSet):
 permission_classes=[HasModulePermission];module_name="stock_transfers"
 def get_queryset(self):
  queryset=super().get_queryset();user=self.request.user
  if getattr(self,"swagger_fake_view",False) or not user.is_authenticated:return queryset.none()
  if user.role=="ADMINISTRATOR" or user.can_access_all_locations or not user.assigned_location_id:return queryset
  return queryset.filter(Q(source_location=user.assigned_location)|Q(destination_location=user.assigned_location))
 def perform_create(self,serializer):serializer.save(transfer_number=generated_number("TRF"),created_by=self.request.user,updated_by=self.request.user)
 @action(detail=True,methods=["post"])
 def submit(self,request,pk=None):return Response(self.get_serializer(_transition(self.get_object(),{"DRAFT"},"SUBMITTED",request.user)).data)
 @action(detail=True,methods=["post"])
 def approve(self,request,pk=None):return Response(self.get_serializer(_transition(self.get_object(),{"DRAFT","SUBMITTED"},"APPROVED",request.user,"approved_by" if hasattr(self.get_object(),"approved_by") else None)).data)
 @action(detail=True,methods=["post"],url_path="dispatch",url_name="dispatch")
 @idempotent_action
 def dispatch_transfer(self,request,pk=None):return Response(self.get_serializer(dispatch_transfer(self.get_object(),request.user,isinstance(self.get_object(),FinishedGoodsTransfer))).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def receive(self,request,pk=None):return Response(self.get_serializer(receive(self.get_object(),request.user,request.data.get("items",[]),isinstance(self.get_object(),FinishedGoodsTransfer))).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):return Response(self.get_serializer(cancel_transfer(self.get_object(),request.user,request.data.get("reason",""))).data)
class MaterialTransferViewSet(BaseTransferViewSet):queryset=MaterialTransfer.objects.prefetch_related("items").order_by("-created_at");serializer_class=MaterialTransferSerializer;module_name="material_transfers"
class FinishedGoodsTransferViewSet(BaseTransferViewSet):queryset=FinishedGoodsTransfer.objects.prefetch_related("items").order_by("-created_at");serializer_class=FinishedGoodsTransferSerializer
