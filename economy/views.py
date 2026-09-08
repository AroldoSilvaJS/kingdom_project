import random # <- Añadir este import al inicio del archivo
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Wallet

def wallet_dashboard(request):
    tg_id = request.GET.get('tg_id')
    wallet = None
    
    if tg_id:
        # get_or_create busca la billetera, y si no existe, la crea al instante.
        wallet, created = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
    return render(request, 'economy/wallet.html', {'tg_id': tg_id, 'wallet': wallet})

def casino_game(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    wallet = None
    resultado = None
    ganancia = 0
    
    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
    if request.method == 'POST':
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            
            # Validaciones de seguridad
            if apuesta <= 0:
                messages.error(request, "La apuesta debe ser mayor a 0.")
            elif apuesta > wallet.balance:
                messages.error(request, "No tienes suficiente oro para esta apuesta.")
            else:
                # El juego: 50% de probabilidad de ganar
                if random.choice([True, False]):
                    # Gana
                    wallet.add_funds(apuesta)
                    resultado = "win"
                    ganancia = apuesta
                else:
                    # Pierde
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    
        except ValueError:
            messages.error(request, "Por favor, ingresa un número válido.")
            
    return render(request, 'economy/casino.html', {
        'tg_id': tg_id, 
        'wallet': wallet,
        'resultado': resultado,
        'ganancia': ganancia
    })