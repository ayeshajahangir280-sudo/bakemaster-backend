from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import Location
from .serializers import LocationSerializer
class LocationViewSet(AuditedModelViewSet):
 queryset=Location.objects.filter(is_active=True); serializer_class=LocationSerializer; permission_classes=[HasModulePermission]; module_name="inventory"; search_fields=["code","name"]; filterset_fields=["location_type","is_active"]
 def perform_destroy(self,instance):
  instance.is_active=False;instance.updated_by=self.request.user;instance.save(update_fields=["is_active","updated_by","updated_at"])
