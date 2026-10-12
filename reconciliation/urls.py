from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health),
    path('import', views.import_statement_view),
]
