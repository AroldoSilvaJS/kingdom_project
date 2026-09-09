import random # <- Añadir este import al inicio del archivo
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Wallet
from django.utils import timezone # Añadir arriba si no lo tienes

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
    
def claim_bonus(request):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        # Usamos la función que creamos en el modelo
        if wallet.can_claim_bonus():
            wallet.add_funds(100) # Premio de 100 de oro
            wallet.last_bonus_claim = timezone.now()
            wallet.save()
            messages.success(request, "¡Has reclamado tu bono diario de 100 🪙 de oro!")
        else:
            messages.error(request, "Aún no han pasado 24 horas desde tu último bono.")
            
        # Lo devolvemos a la bóveda
        return redirect(f'/economy/wallet/?tg_id={tg_id}')
    
def slots_game(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    wallet = None
    resultado = None
    ganancia = 0
    simbolos_finales = ['❔', '❔', '❔']
    animar = False

    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    if request.method == 'POST':
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            if apuesta <= 0:
                messages.error(request, "La apuesta debe ser mayor a 0.")
            elif apuesta > wallet.balance:
                messages.error(request, "No tienes suficiente oro para esta apuesta.")
            else:
                # Cobramos la apuesta por adelantado
                wallet.remove_funds(apuesta)
                
                # Sorteamos los símbolos
                opciones = ['🍒', '💎', '🔔', '🍋', '7️⃣']
                s1, s2, s3 = random.choice(opciones), random.choice(opciones), random.choice(opciones)
                simbolos_finales = [s1, s2, s3]
                
                # Verificamos premios
                if s1 == s2 == s3:
                    # ¡Jackpot! Multiplica por 10
                    ganancia = apuesta * 10
                    wallet.add_funds(ganancia)
                    resultado = "jackpot"
                elif s1 == s2 or s2 == s3 or s1 == s3:
                    # Premio Menor: Multiplica por 2
                    ganancia = apuesta * 2
                    wallet.add_funds(ganancia)
                    resultado = "win"
                else:
                    # Pierde
                    resultado = "lose"
                
                animar = True
        except ValueError:
            messages.error(request, "Apuesta inválida.")

    return render(request, 'economy/slots.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'resultado': resultado,
        'ganancia': ganancia,
        'simbolos': simbolos_finales,
        'animar': animar
    })
    
def get_deck():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [{'suit': s, 'rank': r} for s in suits for r in ranks]
    random.shuffle(deck)
    return deck

def calculate_hand(hand):
    value = 0
    aces = 0
    for card in hand:
        if card['rank'] in ['J', 'Q', 'K']:
            value += 10
        elif card['rank'] == 'A':
            value += 11
            aces += 1
        else:
            value += int(card['rank'])
    # Si nos pasamos de 21 y tenemos Ases, el As pasa a valer 1 en vez de 11
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def blackjack_game(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    
    # Recuperamos la partida actual (si existe) desde la memoria temporal de Django
    game_state = request.session.get('blackjack_state', None)
    resultado = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. INICIAR NUEVO JUEGO
        if action == 'start':
            apuesta = int(request.POST.get('bet_amount', 0))
            if apuesta <= 0 or apuesta > wallet.balance:
                messages.error(request, "Apuesta inválida o no tienes suficiente oro.")
            else:
                wallet.remove_funds(apuesta)
                deck = get_deck()
                
                # Repartir cartas iniciales
                game_state = {
                    'deck': deck,
                    'player': [deck.pop(), deck.pop()],
                    'dealer': [deck.pop(), deck.pop()],
                    'bet': apuesta,
                    'status': 'playing' # playing, player_won, dealer_won, tie
                }
                
                # Revisar si el jugador sacó 21 a la primera (Blackjack Natural)
                if calculate_hand(game_state['player']) == 21:
                    game_state['status'] = 'player_won'
                    wallet.add_funds(int(apuesta * 2.5)) # El Blackjack paga 3:2
                    resultado = "blackjack"
                    
                request.session['blackjack_state'] = game_state
                
        # 2. PEDIR CARTA (HIT)
        elif action == 'hit' and game_state and game_state['status'] == 'playing':
            game_state['player'].append(game_state['deck'].pop())
            
            if calculate_hand(game_state['player']) > 21:
                game_state['status'] = 'dealer_won'
                resultado = "bust"
                
            request.session['blackjack_state'] = game_state
            request.session.modified = True
            
        # 3. PLANTARSE (STAND)
        elif action == 'stand' and game_state and game_state['status'] == 'playing':
            dealer_hand = game_state['dealer']
            
            # El crupier está obligado a pedir carta hasta llegar a 17
            while calculate_hand(dealer_hand) < 17:
                dealer_hand.append(game_state['deck'].pop())
                
            p_val = calculate_hand(game_state['player'])
            d_val = calculate_hand(dealer_hand)
            
            if d_val > 21 or p_val > d_val:
                game_state['status'] = 'player_won'
                wallet.add_funds(game_state['bet'] * 2)
                resultado = "win"
            elif d_val > p_val:
                game_state['status'] = 'dealer_won'
                resultado = "lose"
            else:
                game_state['status'] = 'tie'
                wallet.add_funds(game_state['bet']) # Empate: se devuelve el oro
                resultado = "tie"
                
            request.session['blackjack_state'] = game_state
            request.session.modified = True

    # Calcular valores para mostrar en pantalla
    p_val = calculate_hand(game_state['player']) if game_state else 0
    d_val = calculate_hand(game_state['dealer']) if game_state else 0
    
    return render(request, 'economy/blackjack.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'state': game_state,
        'p_val': p_val,
        'd_val': d_val,
        'resultado': resultado
    })