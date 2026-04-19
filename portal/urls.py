from django.urls import path
from . import views

urlpatterns = [
    path('login/',                          views.portal_login,         name='portal_login'),
    path('logout/',                         views.portal_logout,        name='portal_logout'),
    path('',                                views.dashboard,            name='portal_dashboard'),
    path('users/',                          views.users_view,           name='portal_users'),
    path('users/<int:pk>/',                 views.user_detail,          name='portal_user_detail'),
    path('users/<int:pk>/toggle-active/',   views.toggle_user_active,   name='portal_toggle_user_active'),
    path('listings/',                       views.listings_view,        name='portal_listings'),
    path('listings/<int:pk>/toggle-featured/', views.toggle_featured,  name='portal_toggle_featured'),
    path('listings/<int:pk>/delete/',          views.delete_listing,   name='portal_delete_listing'),
    path('listings/<int:pk>/approve/',         views.approve_listing,  name='portal_approve_listing'),
    path('listings/<int:pk>/reject/',          views.reject_listing,   name='portal_reject_listing'),
    path('listings/<int:pk>/flag/',            views.flag_listing,     name='portal_flag_listing'),
    path('agents/',                            views.agents_view,      name='portal_agents'),
]
