from django.urls import include,path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView,LogoutView,MeView,ChangePasswordView,UserAdminViewSet
r=DefaultRouter(); r.register("users",UserAdminViewSet,basename="auth-user")
urlpatterns=[path("login/",LoginView.as_view()),path("refresh/",TokenRefreshView.as_view()),path("logout/",LogoutView.as_view()),path("me/",MeView.as_view()),path("change-password/",ChangePasswordView.as_view()),path("",include(r.urls))]
