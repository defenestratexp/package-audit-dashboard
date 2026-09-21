"""URL configuration for package-audit-dashboard."""
from django.urls import path, include

urlpatterns = [
    path("", include("packages.urls")),
]
