from django.urls import path

from . import views
from . import community_views

urlpatterns = [
    path('', views.home, name='home'),
    path('listings/', views.listing_list, name='listing_list'),
    path('post/', views.create_listing, name='create_listing'),
    path('saved/', views.saved_listings, name='saved_listings'),
    path('listing/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listing/<int:pk>/edit/', views.edit_listing, name='edit_listing'),
    path('listing/<int:pk>/favourite/', views.toggle_favourite, name='toggle_favourite'),
    path('coming-soon/waitlist/', views.waitlist_signup, name='waitlist_signup'),
    path('listing/<int:pk>/delete/', views.delete_listing, name='delete_listing'),
    path('listing/<int:pk>/inquiries/', views.listing_inquiries, name='listing_inquiries'),
    path('inquiries/<int:inquiry_id>/', views.inquiry_detail, name='inquiry_detail'),
    path('search/guided/', views.guided_search, name='guided_search'),
    path('listing/<int:pk>/estimate/', views.listing_estimate, name='listing_estimate'),
    path('listing/impressions/', views.log_impressions, name='log_impressions'),
    path('listing/estimate-range/', views.listing_estimate_range, name='listing_estimate_range'),

    # ── Community routes ──────────────────────────────────────────────────
    path('communities/', community_views.my_communities, name='my_communities'),
    path('communities/create/', community_views.create_community, name='create_community'),
    path('communities/<int:pk>/', community_views.community_detail, name='community_detail'),
    path('communities/<int:pk>/edit/', community_views.edit_community, name='edit_community'),
    path('communities/<int:community_pk>/floor-plans/add/', community_views.add_floor_plan, name='add_floor_plan'),
    path('communities/floor-plans/<int:pk>/delete/', community_views.delete_floor_plan, name='delete_floor_plan'),
    path('communities/floor-plans/<int:floor_plan_pk>/units/add/', community_views.add_unit, name='add_unit'),
    path('communities/units/<int:pk>/edit/', community_views.edit_unit, name='edit_unit'),
    path('communities/units/<int:pk>/delete/', community_views.delete_unit, name='delete_unit'),
]
