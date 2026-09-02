from django.urls import path

from .views import ERPStateView

urlpatterns = [
    path("erp-state/", ERPStateView.as_view(), name="erp-state"),
]
