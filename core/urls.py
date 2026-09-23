from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.main_menu, name='menu'),
    # Conectamos tu nueva habitación VIP:
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('salon-de-la-fama/', views.leaderboard, name='leaderboard'),
    path('profile/', views.my_profile, name='my_profile'),
]