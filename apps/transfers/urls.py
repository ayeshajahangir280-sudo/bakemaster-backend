from rest_framework.routers import DefaultRouter
from .views import MaterialTransferViewSet,FinishedGoodsTransferViewSet
r=DefaultRouter();r.register("material-transfers",MaterialTransferViewSet);r.register("finished-goods-transfers",FinishedGoodsTransferViewSet);urlpatterns=r.urls
