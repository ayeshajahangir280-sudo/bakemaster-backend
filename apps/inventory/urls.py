from rest_framework.routers import DefaultRouter
from .views import StockAdjustmentViewSet,StockTransactionViewSet,WastageDocumentViewSet
r=DefaultRouter();r.register("inventory/stock-transactions",StockTransactionViewSet,basename="stock-transaction");r.register("inventory/wastage",WastageDocumentViewSet,basename="wastage");r.register("inventory/adjustments",StockAdjustmentViewSet,basename="stock-adjustment");urlpatterns=r.urls
