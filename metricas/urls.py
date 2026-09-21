from django.urls import path

from . import views


app_name = "metricas"


urlpatterns = [
    path(
        "evento/",
        views.registrar,
        name="evento",
    ),
]
