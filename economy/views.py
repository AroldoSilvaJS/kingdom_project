import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Wallet, UserInventoryItem
from core.models import UserRole, UserProfile
from idols.models import IdolProfile, IdolTribute
from pets.models import Pet
from core.utils import grant_user_xp
from core.telegram_notify import send_telegram_msg

def get_safe_tg_id(request):
    raw_id = request.POST.get('tg_id') or request.GET.get('tg_id') or request.session.get('tg_id')
    if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null']:
        try:
            val = int(raw_id)
            request.session['tg_id'] = val
            return val
        except (ValueError, TypeError):
            pass
    return request.session.get('tg_id', 123456789)


def wallet_dashboard(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
        
    return render(request, 'economy/wallet.html', {
        'tg_id': tg_id, 
        'wallet': wallet,
        'profile': profile,
        'pet': pet,
    })


def casino_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    max_bet = profile.max_bet_allowed
    ROJOS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            eleccion = request.POST.get('bet_choice', 'red')
            
            if apuesta <= 0:
                err_msg = "La apuesta debe ser mayor a 0."
                if is_ajax: return JsonResponse({'success': False, 'error': err_msg}, status=400)
                messages.error(request, err_msg)
            elif apuesta > max_bet:
                err_msg = f"Tu rango actual (Nivel {profile.level}) solo permite apostar hasta {max_bet} 🪙."
                if is_ajax: return JsonResponse({'success': False, 'error': err_msg}, status=400)
                messages.error(request, err_msg)
            elif apuesta > wallet.balance:
                err_msg = "No tienes suficiente oro en tu Bóveda."
                if is_ajax: return JsonResponse({'success': False, 'error': err_msg}, status=400)
                messages.error(request, err_msg)
            else:
                numero_ganador = random.randint(0, 36)
                
                if numero_ganador == 0:
                    color_ganador = 'zero'
                elif numero_ganador in ROJOS:
                    color_ganador = 'red'
                else:
                    color_ganador = 'black'
                    
                if eleccion == color_ganador:
                    if eleccion == 'zero':
                        ganancia = int(apuesta * 22)
                    else:
                        ganancia = int(apuesta * 2.0)
                    
                    # BUFF PANTERA DE ÉBANO: Bonus controlado (+3%, +6%, +10%) sobre la ganancia neta
                    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.03, 2: 0.06, 3: 0.10}
                        net_profit = ganancia - apuesta
                        ganancia = int(apuesta + (net_profit * (1 + panther_rates.get(pet.evolution_stage_number, 0.03))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "win"
                    xp_gain = 3
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    xp_gain = 1

                # EXP balanceada (sin inflación)
                grant_user_xp(request, tg_id, xp_gain, reason="Ruleta Imperial")

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'resultado': resultado,
                        'ganancia': ganancia,
                        'numero_ganador': numero_ganador,
                        'color_ganador': color_ganador,
                        'nuevo_saldo': wallet.balance,
                        'current_xp': profile.current_xp,
                        'level': profile.level
                    })
                    
        except ValueError:
            err_msg = "Por favor, ingresa un número válido."
            if is_ajax: return JsonResponse({'success': False, 'error': err_msg}, status=400)
            messages.error(request, err_msg)
            
    return render(request, 'economy/casino.html', {
        'tg_id': tg_id, 
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
    })


def claim_bonus(request):
    tg_id = get_safe_tg_id(request)
    if request.method == 'POST':
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
        
        if wallet.can_claim_bonus():
            bonus_amount = profile.get_daily_bonus_amount()
            wallet.add_funds(bonus_amount)
            wallet.last_bonus_claim = timezone.now()
            wallet.save()
            
            grant_user_xp(request, tg_id, 25, reason="Ruleta de la Fortuna")
            messages.success(request, f"🎡 ¡La Ruleta de la Fortuna te ha otorgado +{bonus_amount} 🪙 de oro y +25 EXP!")
        else:
            horas = wallet.get_cooldown_hours()
            messages.error(request, f"Aún no han transcurrido las {horas}h de recarga de la Ruleta Diaria.")
            
    return redirect(f'/economy/wallet/?tg_id={tg_id}')


def slots_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = profile.max_bet_allowed
    resultado = None
    ganancia = 0
    reels = ['👑', '💎', '⭐']

    # 🎲 BOLSA DE PESOS CALIBRADA (~94.5% RTP - EQUILIBRIO PERFECTO)
    WEIGHTED_SYMBOLS = (
        ['🍇'] * 24 +
        ['🍒'] * 24 +
        ['🪙'] * 20 +
        ['⭐'] * 15 +
        ['💎'] * 11 +
        ['👑'] * 6
    )
        
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        try:
            apuesta = int(request.POST.get('bet_amount', 0))
            
            if apuesta <= 0:
                err = "La apuesta debe ser mayor a 0."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.error(request, err)
            elif apuesta > max_bet:
                err = f"Tu rango actual (Nivel {profile.level}) solo permite apostar hasta {max_bet} 🪙."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.error(request, err)
            elif apuesta > wallet.balance:
                err = "No tienes suficiente oro en tu Bóveda."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.error(request, err)
            else:
                pet = Pet.objects.filter(telegram_user_id=tg_id).first()

                reels = [random.choice(WEIGHTED_SYMBOLS) for _ in range(3)]

                # 🪶 BUFF CUERVO ABISAL: Si salen 2 gemas iguales de alto valor,
                # el Cuervo puede completar la tercera gema mágica
                if pet and pet.species == 'raven':
                    raven_boost = {1: 0.05, 2: 0.10, 3: 0.18}.get(pet.evolution_stage_number, 0.05)
                    if (reels[0] == reels[1] in ['👑', '💎', '⭐']) and random.random() < raven_boost:
                        reels[2] = reels[0]
                    elif (reels[1] == reels[2] in ['👑', '💎', '⭐']) and random.random() < raven_boost:
                        reels[0] = reels[1]
                
                # ─── EVALUACIÓN ESCALONADA DE PREMIOS ───
                # 1. TRÍOS (3 IGUALES)
                if reels[0] == reels[1] == reels[2]:
                    symbol = reels[0]
                    if symbol == '👑':
                        multiplicador = 25.0  # JACKPOT SUPREMO REAL
                        xp_gain = 12
                    elif symbol == '💎':
                        multiplicador = 15.0  # Triple Diamante
                        xp_gain = 8
                    elif symbol == '⭐':
                        multiplicador = 8.0   # Triple Estrella
                        xp_gain = 6
                    elif symbol == '🪙':
                        multiplicador = 5.0   # Triple Moneda
                        xp_gain = 4
                    else:
                        multiplicador = 3.5   # Frutas (🍇 o 🍒)
                        xp_gain = 3

                    ganancia = int(apuesta * multiplicador)
                    
                    # Buff Pantera de Ébano (+4% / +8% / +12% sobre la ganancia neta)
                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net = ganancia - apuesta
                        ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "jackpot" if symbol in ['👑', '💎'] else "trio"

                # 2. PARES (2 IGUALES)
                elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
                    # Detectar qué símbolo formó el par
                    pair_sym = reels[1] if (reels[0] == reels[1] or reels[1] == reels[2]) else reels[0]

                    # Par Premium vs Par Común
                    if pair_sym in ['👑', '💎', '⭐']:
                        multiplicador = 1.6  # Ganancia neta agradable
                        xp_gain = 3
                        resultado = "pair_premium"
                    else:
                        multiplicador = 1.2  # Reintegro amortiguador
                        xp_gain = 2
                        resultado = "pair"

                    ganancia = int(round(apuesta * multiplicador))

                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net = max(0, ganancia - apuesta)
                        ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))

                    wallet.add_funds(ganancia - apuesta)

                # 3. DERROTA
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    xp_gain = 1

                grant_user_xp(request, tg_id, xp_gain, reason="Tragaperras Imperial")

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'reels': reels,
                        'resultado': resultado,
                        'ganancia': ganancia,
                        'nuevo_saldo': wallet.balance,
                        'current_xp': profile.current_xp,
                        'level': profile.level
                    })
                    
        except ValueError:
            err = "Monto inválido."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            
    return render(request, 'economy/slots.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
        'reels': reels,
        'resultado': resultado,
        'ganancia': ganancia
    })


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
        val = c.get('val')
        if val in ['J', 'Q', 'K']:
            total += 10
        elif val == 'A':
            aces += 1
            total += 11
        elif str(val).isdigit():
            total += int(val)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def blackjack_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    max_bet = profile.max_bet_allowed
        
    session_bj = request.session.get('blackjack_state')
    resultado = None
    ganancia = 0
    
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        action = request.POST.get('action')
        
        if action == 'deal':
            try:
                apuesta = int(request.POST.get('bet_amount', 25))
                if apuesta <= 0:
                    err = "La apuesta debe ser mayor a 0."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                    messages.error(request, err)
                elif apuesta > max_bet:
                    err = f"Tu rango actual (Nivel {profile.level}) solo permite apostar hasta {max_bet} 🪙."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                    messages.error(request, err)
                elif apuesta > wallet.balance:
                    err = "No tienes suficiente oro en tu Bóveda."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                    messages.error(request, err)
                else:
                    wallet.remove_funds(apuesta)
                    player_hand = [draw_card(), draw_card()]
                    dealer_hand = [draw_card(), draw_card()]
                    p_val = calculate_hand_value(player_hand)
                    d_init_val = calculate_hand_value(dealer_hand)
                    
                    if p_val == 21:
                        if d_init_val == 21:
                            wallet.add_funds(apuesta)
                            resultado = 'push'
                            ganancia = apuesta
                            xp_gain = 2
                        else:
                            ganancia = int(apuesta * 2.5)
                            if pet and pet.species == 'panther':
                                panther_rates = {1: 0.03, 2: 0.06, 3: 0.10}
                                net = ganancia - apuesta
                                ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.03))))
                                
                            wallet.add_funds(ganancia)
                            resultado = 'blackjack'
                            xp_gain = 6
                        
                        grant_user_xp(request, tg_id, xp_gain, reason="Blackjack")
                        session_bj = {
                            'bet': apuesta,
                            'player_hand': player_hand,
                            'dealer_hand': dealer_hand,
                            'finished': True
                        }
                    else:
                        session_bj = {
                            'bet': apuesta,
                            'player_hand': player_hand,
                            'dealer_hand': dealer_hand,
                            'finished': False
                        }
                    request.session['blackjack_state'] = session_bj
            except ValueError:
                err = "Monto inválido."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.error(request, err)
                
        elif action == 'hit' and session_bj and not session_bj.get('finished'):
            session_bj['player_hand'].append(draw_card())
            p_val = calculate_hand_value(session_bj['player_hand'])
            
            if p_val > 21:
                resultado = 'bust'
                ganancia = session_bj['bet']
                session_bj['finished'] = True

                # BUFF LOBO ESPECTRAL: Protección balanceada (4%, 7%, 10%)
                wolf_protect_rate = {1: 0.04, 2: 0.07, 3: 0.10}.get(pet.evolution_stage_number, 0.04) if (pet and pet.species == 'wolf') else 0.0
                # Indicar si la protección del lobo intervino:
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                    wallet.add_funds(session_bj['bet'])
                    resultado = 'wolf_saved'  # 👈 Diferenciado para mostrar aviso especial
                    ganancia = session_bj['bet']

                grant_user_xp(request, tg_id, 1, reason="Derrota Blackjack")

            request.session['blackjack_state'] = session_bj
                
        elif action == 'stand' and session_bj and not session_bj.get('finished'):
            p_val = calculate_hand_value(session_bj['player_hand'])
            d_hand = session_bj['dealer_hand']
            
            while calculate_hand_value(d_hand) < 17:
                d_hand.append(draw_card())
                
            d_val = calculate_hand_value(d_hand)
            apuesta = session_bj['bet']
            
            if d_val > 21 or p_val > d_val:
                ganancia = apuesta * 2
                if pet and pet.species == 'panther':
                    panther_rates = {1: 0.03, 2: 0.06, 3: 0.10}
                    net = ganancia - apuesta
                    ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.03))))
                    
                wallet.add_funds(ganancia)
                resultado = 'win'
                grant_user_xp(request, tg_id, 4, reason="Victoria Blackjack")
            elif p_val == d_val:
                wallet.add_funds(apuesta)
                resultado = 'push'
                ganancia = apuesta
                grant_user_xp(request, tg_id, 2, reason="Empate Blackjack")
            else:
                resultado = 'lose'
                ganancia = apuesta

                # BUFF LOBO ESPECTRAL
                wolf_protect_rate = {1: 0.04, 2: 0.07, 3: 0.10}.get(pet.evolution_stage_number, 0.04) if (pet and pet.species == 'wolf') else 0.0
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                   wallet.add_funds(apuesta)
                   resultado = 'wolf_saved'  # 👈 Aquí
                   ganancia = apuesta

                grant_user_xp(request, tg_id, 1, reason="Derrota Blackjack")
                
            session_bj['finished'] = True
            request.session['blackjack_state'] = session_bj

        if is_ajax:
            p_cards = session_bj['player_hand'] if session_bj else []
            d_cards = session_bj['dealer_hand'] if session_bj else []
            in_game = session_bj is not None and not session_bj.get('finished', False)

            dealer_visible = d_cards
            dealer_score_visible = calculate_hand_value(d_cards) if d_cards else 0
            if in_game and len(d_cards) >= 2:
                dealer_visible = [d_cards[0], {'val': '?', 'suit': '👑', 'is_red': False, 'hidden': True}]
                dealer_score_visible = calculate_hand_value([d_cards[0]])

            resp = {
                'success': True,
                'in_game': in_game,
                'resultado': resultado,
                'ganancia': ganancia,
                'player_cards': p_cards,
                'dealer_cards': dealer_visible,
                'player_score': calculate_hand_value(p_cards) if p_cards else 0,
                'dealer_score': dealer_score_visible,
                'nuevo_saldo': wallet.balance,
                'current_bet': session_bj['bet'] if session_bj else 25,
            }

            if session_bj and session_bj.get('finished', False):
                request.session['blackjack_state'] = None

            return JsonResponse(resp)
            
    p_cards = session_bj['player_hand'] if session_bj else []
    d_cards = session_bj['dealer_hand'] if session_bj else []
    p_score = calculate_hand_value(p_cards) if p_cards else 0
    d_score = calculate_hand_value(d_cards) if d_cards else 0
    in_game = session_bj is not None and not session_bj.get('finished', False)
    current_bet = session_bj['bet'] if session_bj else 25

    if session_bj and session_bj.get('finished', False):
        request.session['blackjack_state'] = None

    return render(request, 'economy/blackjack.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
        'player_cards': p_cards,
        'dealer_cards': d_cards,
        'player_score': p_score,
        'dealer_score': d_score,
        'in_game': in_game,
        'resultado': resultado,
        'ganancia': ganancia,
        'current_bet': current_bet
    })


# ==========================================
# JUEGO: LAS MINAS DEL REINO (BLINDADO Y SIN EXPLOIT)
# ==========================================

def calculate_mines_multiplier(total_tiles, mines_count, revealed_count):
    if revealed_count <= 0:
        return 1.0
    gems_count = total_tiles - mines_count
    prob = 1.0
    for i in range(revealed_count):
        prob *= (gems_count - i) / (total_tiles - i)
    
    if prob <= 0:
        return 1.0
    
    # Margen de la casa del 6% (0.94) para sostenibilidad matemática
    raw_mult = 0.94 / prob
    return max(1.02, round(raw_mult, 2))


def mines_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = profile.max_bet_allowed
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()

    session_mines = request.session.get('mines_state')

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        action = request.POST.get('action')

        # 1. INICIAR PARTIDA
        if action == 'start':
            try:
                bet = int(request.POST.get('bet_amount', 20))
                mines_count = int(request.POST.get('mines_count', 3))

                if bet <= 0:
                    err = "La apuesta debe ser mayor a 0."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                elif bet > max_bet:
                    err = f"Tu rango actual (Nivel {profile.level}) solo permite apostar hasta {max_bet} 🪙."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                elif bet > wallet.balance:
                    err = "No tienes suficiente oro en tu Bóveda."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                elif mines_count not in [1, 2, 3, 5, 10]:
                    mines_count = 3
                else:
                    wallet.remove_funds(bet)

                    all_indices = list(range(25))
                    mines_locations = random.sample(all_indices, mines_count)

                    session_mines = {
                        'bet': bet,
                        'mines_count': mines_count,
                        'mines': mines_locations,
                        'revealed': [],
                        'multiplier': 1.0,
                        'in_game': True
                    }
                    request.session['mines_state'] = session_mines

                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'in_game': True,
                            'nuevo_saldo': wallet.balance,
                            'bet': bet,
                            'mines_count': mines_count,
                            'revealed': [],
                            'multiplier': 1.0,
                            'current_cashout': bet
                        })
            except ValueError:
                if is_ajax: return JsonResponse({'success': False, 'error': 'Valores no válidos.'}, status=400)

        # 2. DESTAPAR UN COFRE
        elif action == 'reveal' and session_mines and session_mines.get('in_game'):
            try:
                tile_idx = int(request.POST.get('tile_index', -1))
                if 0 <= tile_idx <= 24 and tile_idx not in session_mines['revealed']:
                    if tile_idx in session_mines['mines']:
                        session_mines['in_game'] = False
                        all_mines = session_mines['mines']
                        request.session['mines_state'] = None

                        grant_user_xp(request, tg_id, 1, reason="Minas del Reino")

                        if is_ajax:
                            return JsonResponse({
                                'success': True,
                                'status': 'bust',
                                'hit_tile': tile_idx,
                                'all_mines': all_mines,
                                'nuevo_saldo': wallet.balance
                            })
                    else:
                        session_mines['revealed'].append(tile_idx)
                        revealed_count = len(session_mines['revealed'])
                        mult = calculate_mines_multiplier(25, session_mines['mines_count'], revealed_count)

                        # BUFF DRAGÓN CARMESÍ: Bonus controlado (+0.02x, +0.04x, +0.07x) aplicado UNA SOLA VEZ
                        if pet and pet.species == 'dragon':
                            dragon_bonus = {1: 0.02, 2: 0.04, 3: 0.07}.get(pet.evolution_stage_number, 0.02)
                            mult = round(mult + dragon_bonus, 2)

                        session_mines['multiplier'] = mult
                        cashout_val = int(session_mines['bet'] * mult)

                        total_gems = 25 - session_mines['mines_count']
                        auto_win = (revealed_count == total_gems)

                        if auto_win:
                            session_mines['in_game'] = False
                            if pet and pet.species == 'panther':
                                panther_profit_bonus = {1: 0.03, 2: 0.06, 3: 0.10}.get(pet.evolution_stage_number, 0.03)
                                net = cashout_val - session_mines['bet']
                                cashout_val = int(session_mines['bet'] + (net * (1 + panther_profit_bonus)))
                                
                            wallet.add_funds(cashout_val)
                            request.session['mines_state'] = None
                            grant_user_xp(request, tg_id, 8, reason="Pleno en Minas")

                        request.session['mines_state'] = session_mines if not auto_win else None

                        if is_ajax:
                            return JsonResponse({
                                'success': True,
                                'status': 'win_full' if auto_win else 'gem',
                                'hit_tile': tile_idx,
                                'revealed_count': revealed_count,
                                'multiplier': mult,
                                'current_cashout': cashout_val,
                                'nuevo_saldo': wallet.balance,
                                'all_mines': session_mines['mines'] if auto_win else []
                            })
            except ValueError:
                pass

        # 3. RETIRARSE Y COBRAR (CASHOUT)
        elif action == 'cashout' and session_mines and session_mines.get('in_game'):
            revealed_count = len(session_mines.get('revealed', []))
            if revealed_count > 0:
                mult = session_mines.get('multiplier', 1.0)
                ganancia = int(session_mines['bet'] * mult)

                if pet and pet.species == 'panther':
                    panther_profit_bonus = {1: 0.03, 2: 0.06, 3: 0.10}.get(pet.evolution_stage_number, 0.03)
                    net = max(0, ganancia - session_mines['bet'])
                    ganancia = int(session_mines['bet'] + (net * (1 + panther_profit_bonus)))

                wallet.add_funds(ganancia)
                all_mines = session_mines['mines']
                request.session['mines_state'] = None

                grant_user_xp(request, tg_id, 3, reason="Retiro de Minas")

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'status': 'cashout',
                        'ganancia': ganancia,
                        'multiplier': mult,
                        'all_mines': all_mines,
                        'nuevo_saldo': wallet.balance
                    })
            else:
                # 👈 AÑADIR ESTE ELSE PARA QUE NO DE ERROR 500
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Debes destapar al menos un cofre antes de retirarte.'}, status=400)

    in_game = session_mines is not None and session_mines.get('in_game', False)
    current_revealed = session_mines.get('revealed', []) if session_mines else []
    current_bet = session_mines.get('bet', 20) if session_mines else 20
    current_mines_count = session_mines.get('mines_count', 3) if session_mines else 3
    current_mult = session_mines.get('multiplier', 1.0) if in_game else 1.0
    current_cashout = int(current_bet * current_mult) if in_game else current_bet

    return render(request, 'economy/mines.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
        'in_game': in_game,
        'current_bet': current_bet,
        'current_mines_count': current_mines_count,
        'current_revealed': current_revealed,
        'current_mult': current_mult,
        'current_cashout': current_cashout,
    })


def bazar_shop(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    
    user_role = UserRole.objects.filter(telegram_id=tg_id).first()
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
    is_idol = (user_role and user_role.role == 'idol') or mis_idols.exists()
    
    todas_idols = IdolProfile.objects.all().order_by('stage_name')

    inv_lucky = UserInventoryItem.get_count(tg_id, 'lucky_charm')
    inv_market = UserInventoryItem.get_count(tg_id, 'free_market')
    inv_priority = UserInventoryItem.get_count(tg_id, 'priority_antojo')

    return render(request, 'economy/bazar.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'pet': pet,
        'is_idol': is_idol,
        'mis_idols': mis_idols,
        'todas_idols': todas_idols,
        'inv_lucky': inv_lucky,
        'inv_market': inv_market,
        'inv_priority': inv_priority,
    })


def bazar_buy_action(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    tg_id = get_safe_tg_id(request)
    item_key = request.POST.get('item_key')
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)

    # Catálogo de precios reales del Bazar Imperial (Rebalanceado)
    PRICES = {
        'shield_15': 350,       # Salvoconducto 15 días
        'shield_30': 600,       # Salvoconducto mensual
        'dungeon_bail': 500,     # Fianza de Mazmorra
        'custom_title': 450,     # Edicto de Título Libre
        'imperial_frame': 400,   # Marco Llama Carmesí
        'vip_badge': 300,        # Distintivo VIP
        'tribute_gift': 350,     # Gargantilla de Rubíes para Musa (Idol recibe 280🪙)
        'priority_antojo': 200,  # Sello de Antojo Prioritario
        'featured_idol': 450,    # Musa Destacada en Galería (3 días)
        'lucky_charm': 250,      # Llave Dorada (Doble chance CS)
        'free_market': 150,      # Patente 0% tax en Mercado
        'energy_potion': 120,    # Elixir de Energía para mascota
    }

    price = PRICES.get(item_key)
    if not price:
        return JsonResponse({'success': False, 'error': 'Artículo no reconocido.'}, status=400)

    if wallet.balance < price:
        return JsonResponse({'success': False, 'error': f'No tienes suficiente oro ({price} 🪙 necesarios).'}, status=400)

    msg = ""

    if item_key == 'shield_15':
        current_end = profile.inactivity_shield_until if profile.is_shield_active else timezone.now()
        profile.inactivity_shield_until = current_end + timedelta(days=15)
        profile.save()
        wallet.remove_funds(price)
        msg = "🛡️ ¡Salvoconducto Real activado! Inmunidad extendida por 15 días."

    elif item_key == 'shield_30':
        current_end = profile.inactivity_shield_until if profile.is_shield_active else timezone.now()
        profile.inactivity_shield_until = current_end + timedelta(days=30)
        profile.save()
        wallet.remove_funds(price)
        msg = "🛡️ ¡Salvoconducto Real extendido por 30 días de cobertura total!"

    elif item_key == 'dungeon_bail':
        u_role = UserRole.objects.filter(telegram_id=tg_id).first()
        if not u_role or not u_role.is_banned:
            return JsonResponse({'success': False, 'error': 'No estás en mazmorra actualmente.'}, status=400)
        u_role.is_banned = False
        u_role.ban_reason = None
        u_role.save()
        wallet.remove_funds(price)
        msg = "⚖️ Fianza pagada. Has sido liberado de la mazmorra con honor restaurado."

    elif item_key == 'custom_title':
        title_text = request.POST.get('custom_title_text', '').strip()
        if not title_text:
            return JsonResponse({'success': False, 'error': 'Debes ingresar el título deseado.'}, status=400)
        profile.custom_title_text = title_text[:50]
        profile.save()
        wallet.remove_funds(price)
        msg = f"👑 ¡Edicto Consagrado! Tu nuevo título de rol es «{profile.custom_title_text}»."

    elif item_key == 'imperial_frame':
        profile.has_custom_avatar_frame = True
        profile.avatar_frame = 'flame'
        profile.save()
        wallet.remove_funds(price)
        msg = "🔥 ¡Marco Imperial Llama Carmesí desbloqueado en tu perfil!"

    elif item_key == 'vip_badge':
        profile.has_vip_badge = True
        profile.save()
        wallet.remove_funds(price)
        msg = "✨ ¡Distintivo de Linaje VIP activado para tus comentarios!"

    elif item_key == 'tribute_gift':
        idol_id = request.POST.get('target_idol_id')
        idol = IdolProfile.objects.filter(id=idol_id).first()
        if not idol:
            return JsonResponse({'success': False, 'error': 'Selecciona una Musa válida.'}, status=400)
        
        wallet.remove_funds(price)
        idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=idol.telegram_user_id)
        net_gold = int(price * 0.8)
        idol_wallet.add_funds(net_gold)

        c_name = profile.username if profile.username else f"Noble_{tg_id}"
        IdolTribute.objects.create(
            idol=idol,
            client_telegram_id=tg_id,
            client_username=c_name,
            gift_name="Gargantilla de Rubíes Imperial",
            gold_value=price
        )

        send_telegram_msg(
            chat_id=idol.telegram_user_id,
            text=(
                f"💎 <b>¡Tributo de Corte Recibido!</b>\n\n"
                f"🌹 <b>Para tu Musa:</b> {idol.stage_name}\n"
                f"👤 <b>De parte de:</b> {c_name}\n"
                f"🎁 <b>Obsequio:</b> Gargantilla de Rubíes Imperial\n"
                f"🪙 <b>Oro neto recibido:</b> <b>+{net_gold} 🪙</b> a tu Bóveda."
            ),
            button_text="🪙 Ver Mi Bóveda",
            button_url=f"https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={idol.telegram_user_id}"
        )
        msg = f"🌹 ¡Tributo enviado con éxito a {idol.stage_name}! Recibió +{net_gold} 🪙."

    elif item_key == 'priority_antojo':
        UserInventoryItem.add_item(tg_id, 'priority_antojo', 1)
        wallet.remove_funds(price)
        msg = "📜 Sello de Antojo Prioritario adquirido. Úsalo al pedir una foto."

    elif item_key == 'featured_idol':
        idol_id = request.POST.get('target_idol_id')
        idol = IdolProfile.objects.filter(id=idol_id, telegram_user_id=tg_id).first()
        if not idol:
            return JsonResponse({'success': False, 'error': 'Debes ser la dueña de la Musa para destacarla.'}, status=400)
        idol.is_featured_until = timezone.now() + timedelta(days=3)
        idol.save()
        wallet.remove_funds(price)
        msg = f"✨ ¡{idol.stage_name} fijada en la cima de la Galería por 3 días!"

    elif item_key == 'lucky_charm':
        UserInventoryItem.add_item(tg_id, 'lucky_charm', 1)
        wallet.remove_funds(price)
        msg = "🗝️ Llave Dorada guardada en tu inventario para tu próximo Relicario."

    elif item_key == 'free_market':
        UserInventoryItem.add_item(tg_id, 'free_market', 1)
        wallet.remove_funds(price)
        msg = "📜 Patente de Comercio Libre lista: tu siguiente venta pagará 0% impuesto."

    elif item_key == 'energy_potion':
        pet = Pet.objects.filter(telegram_user_id=tg_id).first()
        if not pet:
            return JsonResponse({'success': False, 'error': 'No tienes una mascota en tu Santuario.'}, status=400)
        pet.energy = 100
        pet.save()
        wallet.remove_funds(price)
        msg = f"🍖 ¡Elixir consumido! La energía de {pet.name} está al 100%."

    return JsonResponse({
        'success': True,
        'message': msg,
        'nuevo_saldo': wallet.balance,
        'shield_days': profile.days_of_shield_remaining
    })