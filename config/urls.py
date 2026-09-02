from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection
from django.db.utils import OperationalError
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

def health(request):
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"status":"error"}, status=503)
    return JsonResponse({"status":"ok"})

urlpatterns=[path("admin/",admin.site.urls),path("api/health/",health,name="health"),path("api/auth/",include("apps.accounts.urls")),path("api/",include("config.api_urls")),path("api/schema/",SpectacularAPIView.as_view(),name="schema"),path("api/docs/",SpectacularSwaggerView.as_view(url_name="schema")),path("api/redoc/",SpectacularRedocView.as_view(url_name="schema"))]
