from django.urls import path

from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('guest/<int:user_id>/', views.guest_conversation, name='guest_conversation'),
    path('live/<int:user_id>/thread/', views.live_thread, name='live_thread'),
    path('live/<int:user_id>/send/', views.live_send, name='live_send'),
    path('<int:user_id>/', views.conversation, name='conversation'),
]
