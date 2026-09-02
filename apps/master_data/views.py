from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from . import models,serializers
def make_view(model,serializer,module):
 class V(AuditedModelViewSet):
  queryset=model.objects.filter(status="ACTIVE"); serializer_class=serializer; permission_classes=[HasModulePermission]; module_name=module; ordering_fields="__all__"
  def perform_destroy(self,instance):
   instance.status="INACTIVE";instance.updated_by=self.request.user;instance.save(update_fields=["status","updated_by","updated_at"])
 return V
SupplierViewSet=make_view(models.Supplier,serializers.SupplierSerializer,"suppliers"); CustomerViewSet=make_view(models.Customer,serializers.CustomerSerializer,"customers"); ItemCategoryViewSet=make_view(models.ItemCategory,serializers.ItemCategorySerializer,"settings"); UnitViewSet=make_view(models.UnitOfMeasurement,serializers.UnitOfMeasurementSerializer,"settings"); TaxRateViewSet=make_view(models.TaxRate,serializers.TaxRateSerializer,"settings"); PaymentMethodViewSet=make_view(models.PaymentMethod,serializers.PaymentMethodSerializer,"settings"); RawMaterialViewSet=make_view(models.RawMaterial,serializers.RawMaterialSerializer,"raw_materials"); FinishedProductViewSet=make_view(models.FinishedProduct,serializers.FinishedProductSerializer,"finished_goods"); ShopProductSettingViewSet=make_view(models.ShopProductSetting,serializers.ShopProductSettingSerializer,"inventory")
