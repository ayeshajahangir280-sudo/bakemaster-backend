from rest_framework.routers import DefaultRouter
from .views import CustomerPaymentViewSet,SupplierPaymentViewSet
r=DefaultRouter();r.register("customer-payments",CustomerPaymentViewSet,basename="customer-payment");r.register("supplier-payments",SupplierPaymentViewSet,basename="supplier-payment");urlpatterns=r.urls
