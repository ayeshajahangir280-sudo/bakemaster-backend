from rest_framework.routers import DefaultRouter
from .views import AuditLogViewSet
r=DefaultRouter();r.register("audit-logs",AuditLogViewSet);urlpatterns=r.urls
