from rest_framework.routers import DefaultRouter
from .views import SalesInvoiceViewSet,SalesReturnViewSet
r=DefaultRouter();r.register("sales-invoices",SalesInvoiceViewSet,basename="sales-invoice");r.register("sales-returns",SalesReturnViewSet,basename="sales-return");urlpatterns=r.urls
