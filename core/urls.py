from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.main_menu, name='menu'),
    path('choose-role/', views.choose_role, name='choose_role'), 
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('salon-de-la-fama/', views.leaderboard, name='leaderboard'),
    path('profile/', views.my_profile, name='my_profile'),
    # 👈 RUTA PARA EL BOT DE TELEGRAM:
    path('telegram-webhook/', views.telegram_webhook, name='telegram_webhook'),
]