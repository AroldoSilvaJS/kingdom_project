from django.urls import path
from . import views

app_name = 'economy'

urlpatterns = [
    path('wallet/', views.wallet_dashboard, name='wallet'),
    path('casino/', views.casino_game, name='casino'), # <- AÑADIR ESTA LÍNEA
]