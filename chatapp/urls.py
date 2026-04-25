from django.urls import path

from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('unread-count/', views.unread_count, name='chat_unread_count'),
    path('guest/<int:user_id>/', views.guest_conversation, name='guest_conversation'),
    path('live/<int:user_id>/thread/', views.live_thread, name='live_thread'),
    path('live/<int:user_id>/send/', views.live_send, name='live_send'),
    path('<int:user_id>/', views.conversation, name='conversation'),

    # Listing-scoped live chat (visitor ↔ owner)
    path('listing/<int:listing_id>/thread/', views.listing_chat_thread, name='listing_chat_thread'),
    path('listing/<int:listing_id>/send/', views.listing_chat_send, name='listing_chat_send'),
    path('listing/<int:listing_id>/typing/', views.listing_chat_typing, name='listing_chat_typing'),

    # Owner: full-page chat with a specific visitor about their listing
    path('listing/<int:listing_id>/with/<int:other_user_id>/', views.owner_chat, name='owner_chat'),
    path('listing/<int:listing_id>/with/<int:other_user_id>/thread/', views.listing_chat_thread, name='owner_listing_chat_thread'),
    path('listing/<int:listing_id>/with/<int:other_user_id>/send/', views.listing_chat_send, name='owner_listing_chat_send'),
    path('listing/<int:listing_id>/with/<int:other_user_id>/typing/', views.listing_chat_typing, name='owner_listing_chat_typing'),
]
