import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Wallet, UserInventoryItem, CourtJob
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


def claim_patron_vault(request):
    """Permite al usuario retirar su 8% acumulado en el Cofre del Mecenas."""
    tg_id = get_safe_tg_id(request)
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        claimed = wallet.claim_patron_vault()

        if claimed > 0:
            msg = f"🏛️ ¡Has retirado +{claimed} 🪙 de tu Cofre del Mecenas a tu Bóveda!"
            if is_ajax:
                return JsonResponse({'success': True, 'claimed': claimed, 'nuevo_saldo': wallet.balance, 'message': msg})
            messages.success(request, msg)
        else:
            err = "Tu Cofre del Mecenas está vacío actualmente. Juega en el casino para acumular retorno."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.info(request, err)

    return redirect(f'/economy/wallet/?tg_id={tg_id}')


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
                # 👑 PILAR 1: Acumular automáticamente 8% en el Cofre del Mecenas
                wallet.accumulate_patron_vault(apuesta)

                # Evaluación de la apuesta
                numero_ganador = random.randint(0, 36)
                
                if numero_ganador == 0:
                    color_ganador = 'zero'
                elif numero_ganador in ROJOS:
                    color_ganador = 'red'
                else:
                    color_ganador = 'black'

                gano = False
                multiplicador = 0.0

                # 1. Apuesta a Color
                if eleccion in ['red', 'black', 'zero']:
                    if eleccion == color_ganador:
                        gano = True
                        multiplicador = 22.0 if eleccion == 'zero' else 2.0

                # 2. Apuesta a Par / Impar
                elif eleccion in ['even', 'odd']:
                    if numero_ganador != 0:
                        es_par = (numero_ganador % 2 == 0)
                        if (eleccion == 'even' and es_par) or (eleccion == 'odd' and not es_par):
                            gano = True
                            multiplicador = 2.0

                # 3. Apuesta a Número Específico (Pleno del 0 al 36)
                elif eleccion == 'number':
                    try:
                        num_apostado = int(request.POST.get('target_number', -1))
                        if num_apostado == numero_ganador:
                            gano = True
                            multiplicador = 30.0  # 🎯 ¡Pleno de la Suerte x30!
                    except ValueError:
                        pass

                if gano:
                    ganancia = int(round(apuesta * multiplicador))
                    # Buff Pantera
                    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net_profit = ganancia - apuesta
                        ganancia = int(apuesta + (net_profit * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "win"
                    xp_gain = 8 if multiplicador >= 20.0 else 3
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    xp_gain = 1

                # EXP balanceada
                grant_user_xp(request, tg_id, xp_gain, reason="Ruleta Imperial")

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'resultado': resultado,
                        'ganancia': ganancia,
                        'numero_ganador': numero_ganador,
                        'color_ganador': color_ganador,
                        'nuevo_saldo': wallet.balance,
                        'patron_vault': wallet.patron_vault,
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
            base_bonus = profile.get_daily_bonus_amount()
            # Multiplicador del Zorro Kitsune (+25% / +45% / +70%)
            multiplier = wallet.get_kitsune_gold_multiplier()
            bonus_amount = int(round(base_bonus * multiplier))

            wallet.add_funds(bonus_amount)
            wallet.last_bonus_claim = timezone.now()
            wallet.save()
            
            grant_user_xp(request, tg_id, 25, reason="Ruleta de la Fortuna")
            extra_msg = f" (¡+{int((multiplier-1)*100)}% por tu Zorro Kitsune!)" if multiplier > 1.0 else ""
            messages.success(request, f"🎡 ¡La Ruleta te ha otorgado +{bonus_amount} 🪙 de oro{extra_msg} y +25 EXP!")
        else:
            messages.error(request, "Ya has reclamado tu ofrenda de hoy. La Ruleta se reinicia cada día a las 12:00 PM.")
            
    return redirect(f'/economy/wallet/?tg_id={tg_id}')


def slots_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = profile.max_bet_allowed
    resultado = None
    ganancia = 0
    reels = ['👑', '💎', '⭐']

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
                # 👑 PILAR 1: Acumular automáticamente 8% en el Cofre del Mecenas
                wallet.accumulate_patron_vault(apuesta)

                pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                reels = [random.choice(WEIGHTED_SYMBOLS) for _ in range(3)]

                # Buff Cuervo Abisal
                if pet and pet.species == 'raven':
                    raven_boost = {1: 0.05, 2: 0.10, 3: 0.18}.get(pet.evolution_stage_number, 0.05)
                    if (reels[0] == reels[1] in ['👑', '💎', '⭐']) and random.random() < raven_boost:
                        reels[2] = reels[0]
                    elif (reels[1] == reels[2] in ['👑', '💎', '⭐']) and random.random() < raven_boost:
                        reels[0] = reels[1]
                
                # 1. TRÍOS
                if reels[0] == reels[1] == reels[2]:
                    symbol = reels[0]
                    if symbol == '👑':
                        multiplicador = 25.0
                        xp_gain = 12
                    elif symbol == '💎':
                        multiplicador = 15.0
                        xp_gain = 8
                    elif symbol == '⭐':
                        multiplicador = 8.0
                        xp_gain = 6
                    elif symbol == '🪙':
                        multiplicador = 5.0
                        xp_gain = 4
                    else:
                        multiplicador = 3.5
                        xp_gain = 3

                    ganancia = int(apuesta * multiplicador)
                    
                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net = ganancia - apuesta
                        ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "jackpot" if symbol in ['👑', '💎'] else "trio"

                # 2. PARES
                elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
                    pair_sym = reels[1] if (reels[0] == reels[1] or reels[1] == reels[2]) else reels[0]
                    if pair_sym in ['👑', '💎', '⭐']:
                        multiplicador = 1.6
                        xp_gain = 3
                        resultado = "pair_premium"
                    else:
                        multiplicador = 1.2
                        xp_gain = 2
                        resultado = "pair"

                    ganancia = int(round(apuesta * multiplicador))

                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net = max(0, ganancia - apuesta)
                        ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))

                    wallet.add_funds(ganancia - apuesta)

                # 👑 PILAR 2: TIRO DE AMORTIGUACIÓN
                elif '👑' in reels or '💎' in reels:
                    reintegro = max(1, int(round(apuesta * 0.5)))
                    wallet.remove_funds(apuesta - reintegro)
                    resultado = "cushion"
                    ganancia = reintegro
                    xp_gain = 2

                # 3. DERROTA TOTAL
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
                        'patron_vault': wallet.patron_vault,
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

# ==========================================
# MINAS DEL REINO: BALANCE JUSTO & PRIMER CLIC SEGURO
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
    
    # 👑 Margen equilibrado al 98% (en lugar de 94%)
    raw_mult = 0.98 / prob
    return max(1.04, round(raw_mult, 2))


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
                    wallet.accumulate_patron_vault(bet)

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
                            'patron_vault': wallet.patron_vault,
                            'bet': bet,
                            'mines_count': mines_count,
                            'revealed': [],
                            'multiplier': 1.0,
                            'current_cashout': bet
                        })
            except ValueError:
                if is_ajax: return JsonResponse({'success': False, 'error': 'Valores no válidos.'}, status=400)

        elif action == 'reveal' and session_mines and session_mines.get('in_game'):
            try:
                tile_idx = int(request.POST.get('tile_index', -1))
                if 0 <= tile_idx <= 24 and tile_idx not in session_mines['revealed']:
                    
                    # 🛡️ MEJORA 1: PRIMER CLIC 100% SEGURO
                    # Si es el primer toque y cayó en una mina, la trasladamos a una casilla libre
                    if len(session_mines['revealed']) == 0 and tile_idx in session_mines['mines']:
                        libres = [i for i in range(25) if i != tile_idx and i not in session_mines['mines']]
                        if libres:
                            session_mines['mines'].remove(tile_idx)
                            session_mines['mines'].append(random.choice(libres))

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
                                'nuevo_saldo': wallet.balance,
                                'patron_vault': wallet.patron_vault
                            })
                    else:
                        session_mines['revealed'].append(tile_idx)
                        revealed_count = len(session_mines['revealed'])
                        mult = calculate_mines_multiplier(25, session_mines['mines_count'], revealed_count)

                        if pet and pet.species == 'dragon':
                            dragon_bonus = {1: 0.04, 2: 0.08, 3: 0.14}.get(pet.evolution_stage_number, 0.04)
                            mult = round(mult + dragon_bonus, 2)

                        session_mines['multiplier'] = mult
                        cashout_val = int(session_mines['bet'] * mult)

                        total_gems = 25 - session_mines['mines_count']
                        auto_win = (revealed_count == total_gems)

                        if auto_win:
                            session_mines['in_game'] = False
                            if pet and pet.species == 'panther':
                                panther_profit_bonus = {1: 0.05, 2: 0.10, 3: 0.18}.get(pet.evolution_stage_number, 0.05)
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
                                'patron_vault': wallet.patron_vault,
                                'all_mines': session_mines['mines'] if auto_win else []
                            })
            except ValueError:
                pass

        elif action == 'cashout' and session_mines and session_mines.get('in_game'):
            revealed_count = len(session_mines.get('revealed', []))
            if revealed_count > 0:
                mult = session_mines.get('multiplier', 1.0)
                ganancia = int(session_mines['bet'] * mult)

                if pet and pet.species == 'panther':
                    panther_profit_bonus = {1: 0.05, 2: 0.10, 3: 0.18}.get(pet.evolution_stage_number, 0.05)
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
                        'nuevo_saldo': wallet.balance,
                        'patron_vault': wallet.patron_vault
                    })
            else:
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


# ==========================================
# BLACKJACK IMPERIAL: ANTIRRACHA & PROTECCIÓN NOBLE
# ==========================================

def blackjack_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    max_bet = profile.max_bet_allowed
        
    session_bj = request.session.get('blackjack_state')
    bj_loss_streak = request.session.get('bj_loss_streak', 0)
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
                    wallet.accumulate_patron_vault(apuesta)

                    player_hand = [draw_card(), draw_card()]
                    dealer_hand = [draw_card(), draw_card()]

                    # 🛡️ BENDICIÓN ANTIRRACHA: Si el usuario lleva 2 o más derrotas seguidas,
                    # asegurar que su mano inicial no sea basura (evitar pares de 5 o 14 incómodos)
                    if bj_loss_streak >= 2:
                        p_check = calculate_hand_value(player_hand)
                        if p_check < 14:
                            # Reemplazar la 2da carta con una carta de alto valor (10, J, Q, K o As)
                            high_vals = ['10', 'J', 'Q', 'K', 'A']
                            suits = ['♠', '♥', '♦', '♣']
                            s = random.choice(suits)
                            v = random.choice(high_vals)
                            player_hand[1] = {'val': v, 'suit': s, 'is_red': s in ['♥', '♦']}

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
                                panther_rates = {1: 0.05, 2: 0.10, 3: 0.15}
                                net = ganancia - apuesta
                                ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.05))))
                                
                            wallet.add_funds(ganancia)
                            resultado = 'blackjack'
                            xp_gain = 6
                            request.session['bj_loss_streak'] = 0
                        
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
                
                # Aumentar racha de derrota
                bj_loss_streak += 1
                request.session['bj_loss_streak'] = bj_loss_streak

                # BUFF LOBO ESPECTRAL
                wolf_protect_rate = {1: 0.10, 2: 0.18, 3: 0.25}.get(pet.evolution_stage_number, 0.10) if (pet and pet.species == 'wolf') else 0.0
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                    wallet.add_funds(session_bj['bet'])
                    resultado = 'wolf_saved'
                    ganancia = session_bj['bet']
                elif bj_loss_streak >= 3:
                    # 🛡️ CONSOLACIÓN DE LA CORONA TRAS 3 DERROTAS
                    rebate = max(1, int(round(session_bj['bet'] * 0.25)))
                    wallet.add_funds(rebate)

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
                    panther_rates = {1: 0.05, 2: 0.10, 3: 0.15}
                    net = ganancia - apuesta
                    ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.05))))
                    
                wallet.add_funds(ganancia)
                resultado = 'win'
                request.session['bj_loss_streak'] = 0
                grant_user_xp(request, tg_id, 4, reason="Victoria Blackjack")
            elif p_val == d_val:
                wallet.add_funds(apuesta)
                resultado = 'push'
                ganancia = apuesta
                grant_user_xp(request, tg_id, 2, reason="Empate Blackjack")
            else:
                resultado = 'lose'
                ganancia = apuesta

                bj_loss_streak += 1
                request.session['bj_loss_streak'] = bj_loss_streak

                wolf_protect_rate = {1: 0.10, 2: 0.18, 3: 0.25}.get(pet.evolution_stage_number, 0.10) if (pet and pet.species == 'wolf') else 0.0
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                    wallet.add_funds(apuesta)
                    resultado = 'wolf_saved'
                    ganancia = apuesta
                elif bj_loss_streak >= 3:
                    # 🛡️ CONSOLACIÓN DE LA CORONA TRAS 3 DERROTAS
                    rebate = max(1, int(round(apuesta * 0.25)))
                    wallet.add_funds(rebate)

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
                'patron_vault': wallet.patron_vault,
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

    PRICES = {
        'shield_15': 350,
        'shield_30': 600,
        'dungeon_bail': 500,
        'custom_title': 450,
        'imperial_frame': 400,
        'vip_badge': 300,
        'tribute_gift': 350,
        'priority_antojo': 200,
        'featured_idol': 450,
        'lucky_charm': 250,
        'free_market': 150,
        'energy_potion': 120,
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


# ==========================================
# LABORES DE LA CORTE (TRABAJOS ACTIVOS)
# ==========================================

JOBS_CATALOG = {
    'cliente': [
        {'key': 'c_guard', 'title': 'Vigilancia de los Pasadizos 🍷', 'duration': 20, 'gold': 15, 'xp': 6, 'desc': 'Ronda de seguridad por los salones clandestinos.'},
        {'key': 'c_trade', 'title': 'Contrabando de Vinos & Especias 🍾', 'duration': 120, 'gold': 45, 'xp': 20, 'desc': 'Gestión de mercancías secretas para los aposentos reales.'},
        {'key': 'c_audit', 'title': 'Inspección Nocturna de Bóvedas 🏦', 'duration': 360, 'gold': 95, 'xp': 45, 'desc': 'Custodia de las arcas imperiales durante la noche.'},
    ],
    'idol': [
        {'key': 'i_glam',  'title': 'Sesión de Maquillaje & Glamour 💄', 'duration': 20, 'gold': 18, 'xp': 8, 'desc': 'Preparación estética para recibir a los nobles.'},
        {'key': 'i_dance', 'title': 'Ensayo de Danza en la Corte 💃', 'duration': 120, 'gold': 50, 'xp': 22, 'desc': 'Perfeccionamiento artístico en los salones de ensayo.'},
        {'key': 'i_gala',  'title': 'Anfitriona de Gala en el Salón Imperial 🌹', 'duration': 360, 'gold': 110, 'xp': 50, 'desc': 'Presidir el banquete principal de la noche.'},
    ]
}

def court_jobs_view(request):
    tg_id = get_safe_tg_id(request)
    if not tg_id:
        return redirect('/')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()

    has_idols = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
    is_idol = (role_obj and role_obj.role == 'idol') or has_idols
    role_key = 'idol' if is_idol else 'cliente'

    active_job = CourtJob.objects.filter(telegram_user_id=tg_id, is_claimed=False).first()
    available_jobs = JOBS_CATALOG.get(role_key, JOBS_CATALOG['cliente'])

    return render(request, 'economy/jobs.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'is_idol': is_idol,
        'active_job': active_job,
        'available_jobs': available_jobs,
    })

def start_court_job(request):
    if request.method == 'POST':
        tg_id = get_safe_tg_id(request)
        role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
        has_idols = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
        is_idol = (role_obj and role_obj.role == 'idol') or has_idols
        role_key = 'idol' if is_idol else 'cliente'

        if CourtJob.objects.filter(telegram_user_id=tg_id, is_claimed=False).exists():
            messages.error(request, "Ya tienes una labor en curso en el Reino.")
            return redirect(f'/economy/jobs/?tg_id={tg_id}')

        job_key = request.POST.get('job_key')
        catalog = {j['key']: j for j in JOBS_CATALOG.get(role_key, [])}
        job_info = catalog.get(job_key)

        if not job_info:
            messages.error(request, "Labor no válida.")
            return redirect(f'/economy/jobs/?tg_id={tg_id}')

        CourtJob.objects.create(
            telegram_user_id=tg_id,
            job_key=job_info['key'],
            title=job_info['title'],
            role_type=role_key,
            duration_minutes=job_info['duration'],
            finishes_at=timezone.now() + timedelta(minutes=job_info['duration']),
            gold_reward=job_info['gold'],
            xp_reward=job_info['xp']
        )
        messages.success(request, f"⏳ Has comenzado la labor: «{job_info['title']}».")

    return redirect(f'/economy/jobs/?tg_id={tg_id}')

def claim_court_job(request):
    if request.method == 'POST':
        tg_id = get_safe_tg_id(request)
        job = CourtJob.objects.filter(telegram_user_id=tg_id, is_claimed=False).first()

        if not job or not job.is_finished():
            messages.error(request, "Esta labor aún no ha finalizado.")
            return redirect(f'/economy/jobs/?tg_id={tg_id}')

        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        wallet.add_funds(job.gold_reward)
        grant_user_xp(request, tg_id, job.xp_reward, reason="Paga de Labor de Corte")

        job.is_claimed = True
        job.save(update_fields=['is_claimed'])

        messages.success(request, f"🪙 ¡Labor cumplida con honor! Has cobrado +{job.gold_reward} 🪙 y +{job.xp_reward} EXP.")

    return redirect(f'/economy/jobs/?tg_id={tg_id}')