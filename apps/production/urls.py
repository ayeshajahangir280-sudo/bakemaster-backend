from rest_framework.routers import DefaultRouter
from .views import ProductionBatchViewSet
r=DefaultRouter();r.register("production-batches",ProductionBatchViewSet);urlpatterns=r.urls
