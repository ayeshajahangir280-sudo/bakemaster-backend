from rest_framework.routers import DefaultRouter
from .views import RecipeViewSet
r=DefaultRouter();r.register("recipes",RecipeViewSet);urlpatterns=r.urls
