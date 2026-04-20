from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('my-listings/', views.my_listings, name='my_listings'),
    path('inquiries/', views.inquiries_overview, name='inquiries_overview'),
    path('performance/', views.performance, name='performance'),
    path('agent/', views.agent_dashboard, name='agent_dashboard'),
]
