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
    numero_ganador = None
    color_ganador = None
    
    # Números rojos estándar de ruleta europea
    ROJOS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    
    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
    if request.method == 'POST':
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            eleccion = request.POST.get('bet_choice', 'red') # 'red', 'black' o 'zero'
            
            if apuesta <= 0:
                messages.error(request, "La apuesta debe ser mayor a 0.")
            elif apuesta > 100:
                messages.error(request, "La apuesta máxima del Casino Imperial es de 100 🪙.")
            elif apuesta > wallet.balance:
                messages.error(request, "No tienes suficiente oro para esta apuesta.")
            else:
                # 🎡 Giro de la Ruleta: 0 al 36 (37 casilleros reales)
                numero_ganador = random.randint(0, 36)
                
                if numero_ganador == 0:
                    color_ganador = 'zero'
                elif numero_ganador in ROJOS:
                    color_ganador = 'red'
                else:
                    color_ganador = 'black'
                    
                # Comprobamos si el jugador acertó
                if eleccion == color_ganador:
                    if eleccion == 'zero':
                        # El Cero verde paga x14
                        ganancia = int(apuesta * 14)
                    else:
                        # Rojo o Negro paga x1.95 (margen imperial del 5%)
                        ganancia = int(apuesta * 1.95)
                        
                    wallet.add_funds(ganancia - apuesta) # Suma neta ganada
                    resultado = "win"
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    
        except ValueError:
            messages.error(request, "Por favor, ingresa un número válido.")
            
    return render(request, 'economy/casino.html', {
        'tg_id': tg_id, 
        'wallet': wallet,
        'resultado': resultado,
        'ganancia': ganancia,
        'numero_ganador': numero_ganador,
        'color_ganador': color_ganador
    })
    
def claim_bonus(request):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        # Usamos la función que creamos en el modelo
        if wallet.can_claim_bonus():
            wallet.add_funds(35) # <- Premio diario equilibrado de 35 de oro
            wallet.last_bonus_claim = timezone.now()
            wallet.save()
            messages.success(request, "¡Has reclamado tu bono diario de 35 🪙 de oro!")
        else:
            messages.error(request, "Aún no han pasado 24 horas desde tu último bono.")
            
        return redirect(f'/economy/wallet/?tg_id={tg_id}')
    
def slots_game(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    wallet = None
    resultado = None
    ganancia = 0
    reels = ['👑', '💎', '⭐'] # Iconos iniciales por defecto
    
    SIMBOLOS = ['👑', '💎', '⭐', '🍇', '🍒', '🪙']
    
    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
    if request.method == 'POST':
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            
            if apuesta <= 0:
                messages.error(request, "La apuesta debe ser mayor a 0.")
            elif apuesta > 100:
                messages.error(request, "La apuesta máxima de la Tragaperras es de 100 🪙.")
            elif apuesta > wallet.balance:
                messages.error(request, "No tienes suficiente oro para esta apuesta.")
            else:
                # 🎰 Generamos los 3 rodillos
                reels = [random.choice(SIMBOLOS) for _ in range(3)]
                
                # Evaluación de premios
                if reels[0] == reels[1] == reels[2]:
                    # Triple coincidencia
                    if reels[0] == '👑':
                        multiplicador = 15 # Jackpot Corona
                    elif reels[0] == '💎':
                        multiplicador = 10 # Jackpot Diamante
                    elif reels[0] == '⭐':
                        multiplicador = 6
                    else:
                        multiplicador = 4 # Frutas o Monedas triples
                        
                    ganancia = apuesta * multiplicador
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "jackpot"
                elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
                    # Par de símbolos iguales (premio consuelo)
                    ganancia = int(apuesta * 1.5)
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "pair"
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    
        except ValueError:
            messages.error(request, "Monto inválido.")
            
    return render(request, 'economy/slots.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'reels': reels,
        'resultado': resultado,
        'ganancia': ganancia
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

def draw_card():
    suits = ['♠', '♥', '♦', '♣']
    values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suit = random.choice(suits)
    val = random.choice(values)
    return {'val': val, 'suit': suit, 'is_red': suit in ['♥', '♦']}

def calculate_hand_value(hand):
    total = 0
    aces = 0
    for c in hand:
        val = c['val']
        if val in ['J', 'Q', 'K']:
            total += 10
        elif val == 'A':
            aces += 1
            total += 11
        else:
            total += int(val)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def blackjack_game(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    wallet = None
    
    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
    # Estado de la mano guardado en sesión
    session_bj = request.session.get('blackjack_state')
    
    resultado = None
    ganancia = 0
    
    if request.method == 'POST':
        action = request.POST.get('action') # 'deal', 'hit', 'stand'
        
        if action == 'deal':
            try:
                apuesta = int(request.POST.get('bet_amount', 25))
                if apuesta <= 0:
                    messages.error(request, "La apuesta debe ser mayor a 0.")
                elif apuesta > 100:
                    messages.error(request, "La apuesta máxima de Blackjack es de 100 🪙.")
                elif apuesta > wallet.balance:
                    messages.error(request, "No tienes suficiente oro en tu Bóveda.")
                else:
                    # Descontamos apuesta inicial
                    wallet.remove_funds(apuesta)
                    
                    # Repartimos 2 cartas a jugador y 2 al croupier
                    player_hand = [draw_card(), draw_card()]
                    dealer_hand = [draw_card(), draw_card()]
                    
                    p_val = calculate_hand_value(player_hand)
                    
                    # Blackjack natural
                    if p_val == 21:
                        ganancia = int(apuesta * 2.5)
                        wallet.add_funds(ganancia)
                        resultado = 'blackjack'
                        session_bj = None
                    else:
                        session_bj = {
                            'bet': apuesta,
                            'player_hand': player_hand,
                            'dealer_hand': dealer_hand,
                            'finished': False
                        }
                    request.session['blackjack_state'] = session_bj
            except ValueError:
                messages.error(request, "Monto inválido.")
                
        elif action == 'hit' and session_bj and not session_bj.get('finished'):
            # Jugador pide carta
            session_bj['player_hand'].append(draw_card())
            p_val = calculate_hand_value(session_bj['player_hand'])
            
            if p_val > 21:
                resultado = 'bust' # Te pasaste
                ganancia = session_bj['bet']
                session_bj['finished'] = True
                request.session['blackjack_state'] = None
            else:
                request.session['blackjack_state'] = session_bj
                
        elif action == 'stand' and session_bj and not session_bj.get('finished'):
            # Jugador se planta -> Croupier roba hasta 17
            p_val = calculate_hand_value(session_bj['player_hand'])
            d_hand = session_bj['dealer_hand']
            
            while calculate_hand_value(d_hand) < 17:
                d_hand.append(draw_card())
                
            d_val = calculate_hand_value(d_hand)
            apuesta = session_bj['bet']
            
            if d_val > 21 or p_val > d_val:
                # Gana el jugador
                ganancia = apuesta * 2
                wallet.add_funds(ganancia)
                resultado = 'win'
            elif p_val == d_val:
                # Empate (push) -> recupera su apuesta
                wallet.add_funds(apuesta)
                resultado = 'push'
                ganancia = apuesta
            else:
                # Gana el croupier
                resultado = 'lose'
                ganancia = apuesta
                
            session_bj['finished'] = True
            request.session['blackjack_state'] = None
            
    # Calculamos valores para el render
    p_cards = session_bj['player_hand'] if session_bj else []
    d_cards = session_bj['dealer_hand'] if session_bj else []
    p_score = calculate_hand_value(p_cards) if p_cards else 0
    d_score = calculate_hand_value(d_cards) if d_cards else 0
    in_game = session_bj is not None and not session_bj.get('finished', False)
    
    return render(request, 'economy/blackjack.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'player_cards': p_cards,
        'dealer_cards': d_cards,
        'player_score': p_score,
        'dealer_score': d_score,
        'in_game': in_game,
        'resultado': resultado,
        'ganancia': ganancia,
        'current_bet': session_bj['bet'] if session_bj else 25
    })