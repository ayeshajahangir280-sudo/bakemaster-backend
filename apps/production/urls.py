from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductionBatchViewSet, ProductionRequirementsView
r=DefaultRouter();r.register("production-batches",ProductionBatchViewSet);urlpatterns=r.urls
urlpatterns += [path("production-requirements/", ProductionRequirementsView.as_view(), name="production-requirements")]
