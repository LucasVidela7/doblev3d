from django.urls import path
from . import views

app_name = "calculadora"

urlpatterns = [
    path("", views.calculadora_precios, name="precios"),
]
