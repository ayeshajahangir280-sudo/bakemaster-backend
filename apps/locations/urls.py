from rest_framework.routers import DefaultRouter
from .views import LocationViewSet
r=DefaultRouter(); r.register("locations",LocationViewSet); urlpatterns=r.urls
