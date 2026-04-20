from django.urls import path

from . import views

urlpatterns = [
    path('', views.listing_list, name='listing_list'),
    path('post/', views.create_listing, name='create_listing'),
    path('saved/', views.saved_listings, name='saved_listings'),
    path('listing/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listing/<int:pk>/edit/', views.edit_listing, name='edit_listing'),
    path('listing/<int:pk>/favourite/', views.toggle_favourite, name='toggle_favourite'),
    path('coming-soon/waitlist/', views.waitlist_signup, name='waitlist_signup'),
    path('listing/<int:pk>/delete/', views.delete_listing, name='delete_listing'),
    path('listing/<int:pk>/inquiries/', views.listing_inquiries, name='listing_inquiries'),
    path('search/guided/', views.guided_search, name='guided_search'),
]
