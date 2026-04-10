from django.urls import path

from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('<int:user_id>/', views.conversation, name='conversation'),
    path('guest/<int:user_id>/', views.guest_conversation, name='guest_conversation'),
]
