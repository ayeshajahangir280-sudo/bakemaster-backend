from rest_framework.routers import DefaultRouter
from .views import PurchaseViewSet
r=DefaultRouter();r.register("purchases",PurchaseViewSet,basename="purchase");urlpatterns=r.urls
