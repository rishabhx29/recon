from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health),
    path('import', views.import_statement_view),
    path('organizations', views.organizations),
    path('transactions', views.transactions),
    path('line-items', views.line_items),
    path('matches/<int:match_id>/approve', views.approve_match_view),
]
