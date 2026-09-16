from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.main_menu, name='menu'),
    # Conectamos tu nueva habitación VIP:
    path('admin-panel/', views.admin_panel, name='admin_panel'),
]