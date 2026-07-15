from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('login/confirm/', views.login_confirm, name='login_confirm'),
    path('login/confirm/resend/', views.login_confirm_resend, name='login_confirm_resend'),
    path('login/confirm/switch/', views.login_confirm_switch, name='login_confirm_switch'),
    path('logout/', views.user_logout, name='logout'),
    path('register/', views.register, name='register'),
    path('register/confirm/', views.register_confirm, name='register_confirm'),
    path('register/confirm/resend/', views.register_confirm_resend, name='register_confirm_resend'),
    path('profile/', views.profile, name='profile'),
    path('profile/update-name/', views.update_name, name='update_name'),
    path('phone/send-code/', views.send_phone_code, name='send_phone_code'),
    path('phone/verify-code/', views.verify_phone_code, name='verify_phone_code'),
    path('notifications/prefs/', views.update_notification_prefs, name='update_notification_prefs'),
    path('my-listings/', views.my_listings, name='my_listings'),
    path('inquiries/', views.inquiries_overview, name='inquiries_overview'),
    path('inquiries/unread-count/', views.unread_inquiry_count, name='inquiry_unread_count'),
    path('performance/', views.performance, name='performance'),
    path('agent/', views.agent_dashboard, name='agent_dashboard'),
]
