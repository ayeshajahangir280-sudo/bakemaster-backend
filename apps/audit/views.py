from rest_framework.viewsets import ReadOnlyModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import AuditLog
from .serializers import AuditLogSerializer
class AuditLogViewSet(ReadOnlyModelViewSet):queryset=AuditLog.objects.all();serializer_class=AuditLogSerializer;permission_classes=[HasModulePermission];module_name="audit";filterset_fields=["user","action","module","record_type"]
