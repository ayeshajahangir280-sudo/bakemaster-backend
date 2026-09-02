from rest_framework.routers import DefaultRouter
from . import views
r=DefaultRouter()
for p,v,b in [("suppliers",views.SupplierViewSet,"supplier"),("customers",views.CustomerViewSet,"customer"),("categories",views.ItemCategoryViewSet,"category"),("units",views.UnitViewSet,"unit"),("tax-rates",views.TaxRateViewSet,"tax"),("payment-methods",views.PaymentMethodViewSet,"method"),("raw-materials",views.RawMaterialViewSet,"material"),("finished-products",views.FinishedProductViewSet,"product"),("shop-product-settings",views.ShopProductSettingViewSet,"shop-setting")]:r.register(p,v,b)
urlpatterns=r.urls
