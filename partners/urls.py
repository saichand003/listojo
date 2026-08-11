from django.urls import path

from . import views

urlpatterns = [
    path('',            views.dashboard,           name='partner_dashboard'),
    path('upload/',     views.upload_inventory,    name='partner_upload'),
    path('connect/',    views.assisted_onboarding, name='partner_onboarding'),
    path('history/',    views.import_history,      name='partner_history'),
]
