from django.urls import path
from . import views

app_name = 'economy'

urlpatterns = [
    path('wallet/', views.wallet_dashboard, name='wallet'),
    path('casino/', views.casino_game, name='casino'),
    path('claim-bonus/', views.claim_bonus, name='claim_bonus'),
    path('slots/', views.slots_game, name='slots'),
    path('blackjack/', views.blackjack_game, name='blackjack'), # <- AÑADIR AQUÍ
]