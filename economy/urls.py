from django.urls import path
from . import views

app_name = 'economy'

urlpatterns = [
    path('wallet/', views.wallet_dashboard, name='wallet'),
    path('casino/', views.casino_game, name='casino'),
    path('claim-bonus/', views.claim_bonus, name='claim_bonus'),
    path('claim-vault/', views.claim_patron_vault, name='claim_vault'),  # 👈 RUTA DEL COFRE DEL MECENAS
    path('slots/', views.slots_game, name='slots'),
    path('blackjack/', views.blackjack_game, name='blackjack'),
    path('mines/', views.mines_game, name='mines'),
    path('bazar/', views.bazar_shop, name='bazar'),
    path('bazar/buy/', views.bazar_buy_action, name='bazar_buy'),
    path('jobs/', views.court_jobs_view, name='jobs'),
    path('jobs/start/', views.start_court_job, name='start_job'),
    path('jobs/claim/', views.claim_court_job, name='claim_job'),
]