from django.urls import path

from . import views

urlpatterns = [
    path('apply/',      views.apply_to_partner,    name='partner_apply'),
    path('',            views.dashboard,           name='partner_dashboard'),
    path('upload/',     views.upload_inventory,    name='partner_upload'),
    path('connect/',    views.assisted_onboarding, name='partner_onboarding'),
    path('history/',    views.import_history,      name='partner_history'),
    path('communities/<int:pk>/media-rights/', views.confirm_media_rights,
         name='partner_confirm_media_rights'),
]
