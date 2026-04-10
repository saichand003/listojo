from django.urls import path

from . import views

urlpatterns = [
    path('', views.listing_list, name='listing_list'),
    path('post/', views.create_listing, name='create_listing'),
    path('listing/<int:pk>/', views.listing_detail, name='listing_detail'),
]
