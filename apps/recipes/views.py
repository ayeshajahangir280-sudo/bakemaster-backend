from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import Recipe
from .serializers import RecipeSerializer
class RecipeViewSet(AuditedModelViewSet):
 queryset=Recipe.objects.exclude(status__in=["INACTIVE","ARCHIVED"]).prefetch_related("items");serializer_class=RecipeSerializer;permission_classes=[HasModulePermission];module_name="recipes"
 def perform_destroy(self,instance):
  instance.status="INACTIVE";instance.is_default=False;instance.updated_by=self.request.user;instance.save(update_fields=["status","is_default","updated_by","updated_at"])
