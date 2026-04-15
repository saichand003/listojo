from django.urls import path

from . import views

urlpatterns = [
    path('', views.listing_list, name='listing_list'),
    path('post/', views.create_listing, name='create_listing'),
    path('saved/', views.saved_listings, name='saved_listings'),
    path('listing/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listing/<int:pk>/edit/', views.edit_listing, name='edit_listing'),
    path('listing/<int:pk>/favourite/', views.toggle_favourite, name='toggle_favourite'),
]
