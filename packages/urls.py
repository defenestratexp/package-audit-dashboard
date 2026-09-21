"""URL configuration for packages app."""
from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.dashboard, name="dashboard"),
    path("host/<str:hostname>/", views.host_detail, name="host_detail"),
    path("search/", views.search, name="search"),
    path("compare/", views.compare, name="compare"),
    path("security/", views.security_packages, name="security_packages"),
    path("api/hosts/", views.api_hosts, name="api_hosts"),
    path("api/host/<str:hostname>/", views.api_host_packages, name="api_host_packages"),
]
