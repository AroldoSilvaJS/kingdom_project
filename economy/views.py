# 1. Librería estándar de Python
import random
from datetime import timedelta

# 2. Django Core & Utilidades
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

# 3. Modelos de otras Apps del Reino
from core.models import UserProfile, UserRole
from idols.models import IdolProfile, IdolTribute
from pets.models import Pet

# 4. Utilidades y Helpers
from core.telegram_notify import send_telegram_msg
from core.utils import grant_user_xp
from idols.views import check_is_staff_or_admin, optimize_uploaded_image

# 5. Modelos de la App Actual (Economy)
from .models import (
    BazarCollectible,
    CourtJob,
    UserCollectible,
    UserInventoryItem,
    Wallet, CollectibleSeries,
)


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
    tg_id = get_safe_tg_id(request)
    if request.method == 'POST':
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        if wallet.patron_vault > 0:
            cobrado = wallet.claim_patron_vault()
            grant_user_xp(request, tg_id, max(1, cobrado // 10), reason="Cofre del Mecenas")
            messages.success(request, f"💎 ¡Has reclamado {cobrado} 🪙 del Cofre del Mecenas!")
        else:
            messages.warning(request, "Tu Cofre del Mecenas está vacío actualmente.")
            
    return redirect(f'/economy/wallet/?tg_id={tg_id}')


# ==============================================================================
# 🎡 RULETA IMPERIAL (CASINO REAL SINCRONIZADO CON casino.html)
# ==============================================================================
def casino_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    max_bet = max(100, getattr(profile, 'max_bet_allowed', 100))
    ROJOS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    NEGROS = [n for n in range(1, 37) if n not in ROJOS]
    roulette_streak = request.session.get('roulette_streak', 0)
        
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
                wallet.accumulate_patron_vault(apuesta)
                
                # Alternancia dinámica anti-rachas negativas
                force_win = False
                if roulette_streak >= 2 and random.random() < 0.65:
                    force_win = True

                if force_win and eleccion in ['red', 'black', 'even', 'odd']:
                    if eleccion == 'red':
                        numero_ganador = random.choice(ROJOS)
                    elif eleccion == 'black':
                        numero_ganador = random.choice(NEGROS)
                    elif eleccion == 'even':
                        numero_ganador = random.choice([n for n in range(1, 37) if n % 2 == 0])
                    else:
                        numero_ganador = random.choice([n for n in range(1, 37) if n % 2 != 0])
                else:
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
                # 3. Apuesta a Número Específico (Pleno x30)
                elif eleccion == 'number':
                    try:
                        num_apostado = int(request.POST.get('target_number', -1))
                        if num_apostado == numero_ganador:
                            gano = True
                            multiplicador = 30.0
                    except ValueError:
                        pass

                if gano:
                    ganancia = int(round(apuesta * multiplicador))
                    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net_profit = ganancia - apuesta
                        ganancia = int(apuesta + (net_profit * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "win"
                    xp_gain = 8 if multiplicador >= 20.0 else 3
                    request.session['roulette_streak'] = 0
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    xp_gain = 1
                    request.session['roulette_streak'] = roulette_streak + 1

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


# ==============================================================================
# 🎰 TRAGAPERRAS IMPERIAL (SINCRONIZADO CON slots.html)
# ==============================================================================
def slots_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = max(100, getattr(profile, 'max_bet_allowed', 100))
    slots_losses = request.session.get('slots_losses', 0)

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
                wallet.accumulate_patron_vault(apuesta)
                pet = Pet.objects.filter(telegram_user_id=tg_id).first()

                # Alternancia dinámica anti-racha
                if slots_losses >= 2 and random.random() < 0.65:
                    sym = random.choice(['🍇', '🍒', '🪙', '⭐'])
                    reels = [sym, sym, random.choice(WEIGHTED_SYMBOLS)]
                else:
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
                    multiplicador = {'👑': 25.0, '💎': 15.0, '⭐': 8.0, '🪙': 5.0}.get(symbol, 3.5)
                    xp_gain = 12 if symbol == '👑' else 4
                    ganancia = int(apuesta * multiplicador)

                    if pet and pet.species == 'panther':
                        panther_rates = {1: 0.04, 2: 0.08, 3: 0.12}
                        net = ganancia - apuesta
                        ganancia = int(apuesta + (net * (1 + panther_rates.get(pet.evolution_stage_number, 0.04))))
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "jackpot" if symbol in ['👑', '💎'] else "trio"
                    request.session['slots_losses'] = 0

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
                    request.session['slots_losses'] = 0

                # 3. AMORTIGUACIÓN
                elif '👑' in reels or '💎' in reels:
                    reintegro = max(1, int(round(apuesta * 0.5)))
                    wallet.remove_funds(apuesta - reintegro)
                    resultado = "cushion"
                    ganancia = reintegro
                    xp_gain = 2
                    request.session['slots_losses'] = 0

                # 4. DERROTA
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta
                    xp_gain = 1
                    request.session['slots_losses'] = slots_losses + 1

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


# ==============================================================================
# 🃏 MOTOR DE CARTAS
# ==============================================================================
def draw_card():
    suits = ['♠', '♥', '♦', '♣']
    values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suit = random.choice(suits)
    val = random.choice(values)
    is_red = suit in ['♥', '♦']
    points = 10 if val in ['10', 'J', 'Q', 'K'] else (11 if val == 'A' else int(val))
    return {'val': val, 'suit': suit, 'is_red': is_red, 'points': points}


def calculate_hand_value(hand):
    total = sum(c['points'] for c in hand)
    aces = sum(1 for c in hand if c['val'] == 'A')
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


# ==============================================================================
# 💣 MINAS DEL REINO (SINCRONIZADO CON mines.html)
# ==============================================================================
def calculate_mines_multiplier(total_tiles, mines_count, revealed_count):
    if revealed_count == 0:
        return 1.0
    safe_tiles = total_tiles - mines_count
    prob = 1.0
    for i in range(revealed_count):
        prob *= (safe_tiles - i) / (total_tiles - i)
    raw_mult = 0.98 / prob
    return max(1.04, round(raw_mult, 2))


def mines_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = max(100, getattr(profile, 'max_bet_allowed', 100))
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()

    session_mines = request.session.get('mines_state')

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        action = request.POST.get('action')

        if action == 'start':
            try:
                bet = int(request.POST.get('bet_amount', 0))
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
                    
                    # Primer clic siempre seguro
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


# ==============================================================================
# 🃏 BLACKJACK DE LA CORTE (SINCRONIZADO CON blackjack.html)
# ==============================================================================
def blackjack_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    max_bet = max(100, getattr(profile, 'max_bet_allowed', 100))
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    bj_losses = request.session.get('bj_loss_streak', 0)

    session_bj = request.session.get('blackjack_state')
    resultado = None
    ganancia = 0

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        action = request.POST.get('action')

        if action == 'deal':
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
                    wallet.remove_funds(apuesta)
                    wallet.accumulate_patron_vault(apuesta)

                    player_hand = [draw_card(), draw_card()]
                    dealer_hand = [draw_card(), draw_card()]

                    # Alternancia para evitar rachas frustrantes (Blindada con 'points' e 'is_red' dinámico)
                    if bj_losses >= 2:
                        p_check = calculate_hand_value(player_hand)
                        if p_check < 15:
                            high_vals = ['10', 'J', 'Q', 'K', 'A']
                            suits = ['♠', '♥', '♦', '♣']
                            chosen_suit = random.choice(suits)
                            chosen_val = random.choice(high_vals)
                            is_red_card = chosen_suit in ['♥', '♦']
                            pts = 10 if chosen_val in ['10', 'J', 'Q', 'K'] else 11
                            player_hand[1] = {
                                'val': chosen_val,
                                'suit': chosen_suit,
                                'is_red': is_red_card,
                                'points': pts
                            }

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
                request.session['bj_loss_streak'] = bj_losses + 1

                # Buff de protección del Lobo
                wolf_protect_rate = {1: 0.10, 2: 0.18, 3: 0.25}.get(pet.evolution_stage_number, 0.10) if (pet and pet.species == 'wolf') else 0.0
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                    wallet.add_funds(session_bj['bet'])
                    resultado = 'wolf_saved'
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
                request.session['bj_loss_streak'] = bj_losses + 1

                wolf_protect_rate = {1: 0.10, 2: 0.18, 3: 0.25}.get(pet.evolution_stage_number, 0.10) if (pet and pet.species == 'wolf') else 0.0
                if pet and pet.species == 'wolf' and random.random() < wolf_protect_rate:
                    wallet.add_funds(apuesta)
                    resultado = 'wolf_saved'
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


# ==============================================================================
# 🏪 EL BAZAR & ARTÍCULOS VIP
# ==============================================================================
BAZAR_ITEMS = [
    {
        'code': 'shield_15',
        'name': 'Escudo Protector (15 días)',
        'description': 'Inmunidad total a la pérdida de rango o recompensas durante 15 días en caso de inactividad.',
        'price': 350,
        'icon': 'fa-solid fa-shield-halved',
        'color': 'border-amber-500/40 text-amber-300',
        'type': 'status'
    },
    {
        'code': 'shield_30',
        'name': 'Escudo Protector Imperial (30 días)',
        'description': 'Un mes entero de protección soberana ante cualquier ausencia de la corte.',
        'price': 600,
        'icon': 'fa-solid fa-shield-virus',
        'color': 'border-yellow-500/50 text-yellow-300',
        'type': 'status'
    },
    {
        'code': 'custom_title',
        'name': 'Bula de Título Personalizado',
        'description': 'Graba en tu perfil un epíteto o distinción única redactada por ti.',
        'price': 450,
        'icon': 'fa-solid fa-feather-pointed',
        'color': 'border-rose-500/40 text-rose-300',
        'type': 'customization'
    },
    {
        'code': 'imperial_frame',
        'name': 'Marco de Avatar Imperial',
        'description': 'Engalana tu presencia visual con los marcos de oro pulido y gemas dinásticas.',
        'price': 400,
        'icon': 'fa-solid fa-gem',
        'color': 'border-purple-500/40 text-purple-300',
        'type': 'customization'
    },
    {
        'code': 'vip_badge',
        'name': 'Insignia de Linaje VIP',
        'description': 'Una medalla de honor perpetua visible en tu perfil público ante todos los nobles.',
        'price': 300,
        'icon': 'fa-solid fa-award',
        'color': 'border-blue-500/40 text-blue-300',
        'type': 'customization'
    },
    {
        'code': 'priority_antojo',
        'name': 'Sello de Antojo Prioritario',
        'description': 'Tus peticiones de antojos a las Idols reciben respuesta urgente en la cúspide.',
        'price': 200,
        'icon': 'fa-solid fa-bell-concierge',
        'color': 'border-pink-500/40 text-pink-300',
        'type': 'consumable'
    },
    {
        'code': 'lucky_charm',
        'name': 'Talismán de la Fortuna',
        'description': 'Aumenta sutilmente la bendición de tiradas y recompensas en el casino.',
        'price': 250,
        'icon': 'fa-solid fa-clover',
        'color': 'border-emerald-500/40 text-emerald-300',
        'type': 'consumable'
    },
    {
        'code': 'free_market',
        'name': 'Pase de Libre Comercio',
        'description': 'Exención de tributos del reino en tus próximas compras o ventas.',
        'price': 150,
        'icon': 'fa-solid fa-coins',
        'color': 'border-yellow-400 text-yellow-300',
        'type': 'consumable'
    },
]


def bazar_shop(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    # Inventario actual del usuario
    inventory_items = UserInventoryItem.objects.filter(telegram_user_id=tg_id)
    inv_dict = {item.item_code: item.quantity for item in inventory_items}
    
    # Coleccionables y Colecciones Pop Mart disponibles en la Boutique
    collectibles = BazarCollectible.objects.filter(is_active=True).select_related('series').order_by('-created_at')
    series_list = CollectibleSeries.objects.filter(is_active=True).prefetch_related('items').order_by('-created_at')
    user_collectibles = UserCollectible.objects.filter(telegram_user_id=tg_id).select_related('item', 'item__series')
    user_item_ids = set(user_collectibles.values_list('item_id', flat=True))

    # Progreso de cada serie para el usuario (ej: 3/9)
    for s in series_list:
        s_items = list(s.items.filter(is_active=True))
        s.items_cache = s_items
        s.owned_count = sum(1 for it in s_items if it.id in user_item_ids)
    is_staff = check_is_staff_or_admin(tg_id)

    from idols.models import IdolProfile
    todas_idols = IdolProfile.objects.all().order_by('stage_name')
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id).order_by('stage_name') if tg_id else IdolProfile.objects.none()

    # Detección limpia de rol Idol para desbloquear pestaña exclusiva
    is_idol = False
    if tg_id:
        try:
            role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
            if (role_obj and role_obj.role == 'idol') or mis_idols.exists():
                is_idol = True
        except Exception:
            is_idol = mis_idols.exists()

    return render(request, 'economy/bazar.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'bazar_items': BAZAR_ITEMS,
        'inventory': inv_dict,
        'collectibles': collectibles,
        'boutique_items': collectibles,
        'user_collectibles': user_collectibles,
        'my_collectibles': user_collectibles,
        'todas_idols': todas_idols,
        'mis_idols': mis_idols,
        'is_idol': is_idol,
        'inv_priority': inv_dict.get('priority_antojo', 0),
        'inv_lucky': inv_dict.get('lucky_charm', 0),
        'inv_market': inv_dict.get('free_market', 0),
        'is_staff': is_staff,
        'is_admin': is_staff,
        'series_list': series_list,
        'user_item_ids': user_item_ids,
    })


def bazar_buy_action(request):
    if request.method != 'POST':
        return redirect('/economy/bazar/')
        
    tg_id = get_safe_tg_id(request)
    item_code = request.POST.get('item_code') or request.POST.get('item_key')
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    # ⚖️ LIBERACIÓN DE MAZMORRA (FIANZA REAL DE 500 🪙)
    if item_code == 'dungeon_bail':
        BAIL_PRICE = 500
        if wallet.balance < BAIL_PRICE:
            err = f"No tienes suficiente oro ({wallet.balance}/{BAIL_PRICE} 🪙) para pagar la fianza."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
        with transaction.atomic():
            wallet.remove_funds(BAIL_PRICE)
            UserRole.objects.filter(telegram_id=tg_id).update(is_banned=False, ban_reason=None)
        
        grant_user_xp(request, tg_id, 15, reason="Pago de Fianza Real")
        msg = "⚖️ ¡Fianza aceptada por la Corona! Has sido indultado y liberado de las mazmorras."
        if is_ajax:
            return JsonResponse({'success': True, 'message': msg, 'nuevo_saldo': wallet.balance})
        messages.success(request, msg)
        return redirect(f'/?tg_id={tg_id}')

    # 🌹 TRIBUTO A MUSA (350 🪙 -> 280 🪙 netos a su Bóveda)
    if item_code == 'tribute_gift':
        TRIBUTE_PRICE = 350
        NET_TRIBUTE = 280
        target_idol_id = request.POST.get('target_idol_id')
        from idols.models import IdolProfile
        idol = IdolProfile.objects.filter(id=target_idol_id).first() if target_idol_id else None
        if not idol:
            err = "Debes seleccionar una Musa válida de la corte para entregar el tributo."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        if wallet.balance < TRIBUTE_PRICE:
            err = f"No tienes suficiente oro ({wallet.balance}/{TRIBUTE_PRICE} 🪙)."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        with transaction.atomic():
            wallet.remove_funds(TRIBUTE_PRICE)
            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=idol.telegram_user_id)
            idol_wallet.add_funds(NET_TRIBUTE)
        grant_user_xp(request, tg_id, 30, reason=f"Tributo a Musa {idol.stage_name}")
        from core.telegram_notify import send_telegram_msg
        send_telegram_msg(
            chat_id=idol.telegram_user_id,
            text=f"🎁 <b>¡Tributo Real Recibido!</b>\n\nUn noble te ha enviado una Gargantilla de Rubíes desde el Bazar Real.\nSe han acreditado <b>+{NET_TRIBUTE} 🪙</b> en tu Bóveda Imperial."
        )
        msg = f"💎 Has enviado un distinguido tributo a {idol.stage_name}. ¡Recibió {NET_TRIBUTE} 🪙 netos en su Bóveda!"
        if is_ajax: return JsonResponse({'success': True, 'message': msg, 'nuevo_saldo': wallet.balance})
        messages.success(request, msg)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    # 🌟 MUSA DESTACADA (450 🪙 por 3 días)
    if item_code == 'featured_idol':
        FEATURE_PRICE = 450
        target_idol_id = request.POST.get('target_idol_id')
        from idols.models import IdolProfile
        idol = IdolProfile.objects.filter(id=target_idol_id, telegram_user_id=tg_id).first() if target_idol_id else None
        if not idol:
            err = "Selecciona una Musa consagrada bajo tu tutela."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        if wallet.balance < FEATURE_PRICE:
            err = f"No tienes suficiente oro ({wallet.balance}/{FEATURE_PRICE} 🪙)."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        with transaction.atomic():
            wallet.remove_funds(FEATURE_PRICE)
            from django.utils import timezone
            from datetime import timedelta
            now_feat = timezone.now()
            base_time = idol.is_featured_until if (idol.is_featured_until and idol.is_featured_until > now_feat) else now_feat
            idol.is_featured_until = base_time + timedelta(days=3)
            idol.save(update_fields=['is_featured_until'])
        grant_user_xp(request, tg_id, 40, reason=f"Musa Destacada: {idol.stage_name}")
        msg = f"✨ ¡{idol.stage_name} ahora resplandece como Musa Destacada en la Galería del Reino!"
        if is_ajax: return JsonResponse({'success': True, 'message': msg, 'nuevo_saldo': wallet.balance})
        messages.success(request, msg)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    # 🧪 ELIXIR DE VITALIDAD (120 🪙 -> Restaura energía de mascota al 100%)
    if item_code == 'energy_potion':
        POTION_PRICE = 120
        from pets.models import Pet
        pet = Pet.objects.filter(telegram_user_id=tg_id).first()
        if not pet:
            err = "No tienes una mascota en tu Santuario para vigorizar."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        if wallet.balance < POTION_PRICE:
            err = f"No tienes suficiente oro ({wallet.balance}/{POTION_PRICE} 🪙)."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        with transaction.atomic():
            wallet.remove_funds(POTION_PRICE)
            pet.energy = 100
            pet.save(update_fields=['energy'])
        grant_user_xp(request, tg_id, 10, reason="Elixir de Vitalidad")
        msg = f"🧪 ¡{pet.evolved_name} ha bebido el Elixir! Su energía se ha restaurado al 100%."
        if is_ajax: return JsonResponse({'success': True, 'message': msg, 'nuevo_saldo': wallet.balance})
        messages.success(request, msg)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    matched_item = next((item for item in BAZAR_ITEMS if item['code'] == item_code), None)
    
    if not matched_item:
        err = "El artículo solicitado no existe en los estantes del Bazar."
        if is_ajax:
            return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    price = matched_item['price']
    if wallet.balance < price:
        err = f"No tienes suficiente oro imperial ({wallet.balance}/{price} 🪙)."
        if is_ajax:
            return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    now = timezone.now()
    success_msg = ""

    # Procesar compra según categoría
    if item_code == 'shield_15':
        current_until = profile.inactivity_shield_until if (profile.inactivity_shield_until and profile.inactivity_shield_until > now) else now
        profile.inactivity_shield_until = current_until + timedelta(days=15)
        profile.save()
        wallet.remove_funds(price)
        success_msg = "🛡️ ¡Inmunidad adquirida! Tu rango está protegido por 15 días."

    elif item_code == 'shield_30':
        current_until = profile.inactivity_shield_until if (profile.inactivity_shield_until and profile.inactivity_shield_until > now) else now
        profile.inactivity_shield_until = current_until + timedelta(days=30)
        profile.save()
        wallet.remove_funds(price)
        success_msg = "🛡️ ¡Inmunidad Imperial concedida! Tu rango está protegido por 30 días."

    elif item_code == 'custom_title':
        custom_txt = request.POST.get('custom_title_text', '').strip()
        if not custom_txt:
            err = "Debes ingresar el texto para tu nuevo título personalizado."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.warning(request, err)
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
        if len(custom_txt) > 60:
            custom_txt = custom_txt[:60]
        profile.custom_title_text = custom_txt
        profile.save()
        wallet.remove_funds(price)
        success_msg = f"📜 ¡Título proclamado con éxito: «{custom_txt}»!"

    elif item_code == 'imperial_frame':
        profile.has_custom_avatar_frame = True
        profile.save()
        wallet.remove_funds(price)
        success_msg = "👑 ¡Acceso a Marcos Imperiales desbloqueado! Puedes elegirlo en tu perfil."

    elif item_code == 'vip_badge':
        profile.has_vip_badge = True
        profile.save()
        wallet.remove_funds(price)
        success_msg = "🎖️ ¡Insignia de Linaje VIP otorgada permanentemente en tu blasón!"

    elif matched_item['type'] == 'consumable':
        UserInventoryItem.add_item(tg_id, item_code, 1)
        wallet.remove_funds(price)
        success_msg = f"✨ Has adquirido {matched_item['name']}. Ha sido guardado en tus alforjas."

    grant_user_xp(request, tg_id, max(5, price // 20), reason=f"Compra en Bazar: {matched_item['name']}")

    if is_ajax:
        return JsonResponse({'success': True, 'message': success_msg, 'nuevo_saldo': wallet.balance})

    messages.success(request, success_msg)
    return redirect(f'/economy/bazar/?tg_id={tg_id}')


# ==============================================================================
# 🪔 LABORES DE LA CORTE (EQUILIBRADAS, PICARONAS Y CON DISTINCIÓN DE ROLES)
# ==============================================================================

JOBS_CATALOG = [
    # --- LABORES PARA NOBLES / CLIENTES ---
    {
        'id': 'noble_bath_oil',
        'key': 'noble_bath_oil',
        'role_type': 'cliente',
        'role_label': 'Noble / Cliente',
        'title': 'Selección de Aceites para el Baño Real',
        'description': 'Elegir esencias aromáticas exóticas para el tocador privado de los nobles.',
        'duration_minutes': 15,
        'gold_reward': 55,
        'reward_gold': 55,
        'xp_reward': 30,
        'reward_xp': 30,
        'min_level': 1,
        'icon': 'fa-solid fa-bottle-droplet',
        'emoji': '🏺',
        'badge_color': 'bg-amber-900/60 text-amber-300 border-amber-700/50',
    },
    {
        'id': 'noble_wine_tasting',
        'key': 'noble_wine_tasting',
        'role_type': 'cliente',
        'role_label': 'Noble / Cliente',
        'title': 'Cata de Vinos Afrodisíacos',
        'description': 'Degustar cosechas reservadas con toques de canela y miel para banquetes de medianoche.',
        'duration_minutes': 30,
        'gold_reward': 130,
        'reward_gold': 130,
        'xp_reward': 70,
        'reward_xp': 70,
        'min_level': 1,
        'icon': 'fa-solid fa-wine-glass-empty',
        'emoji': '🍷',
        'badge_color': 'bg-rose-900/60 text-rose-300 border-rose-700/50',
    },
    {
        'id': 'noble_harem_inspection',
        'key': 'noble_harem_inspection',
        'role_type': 'cliente',
        'role_label': 'Noble / Cliente',
        'title': 'Custodia de las Cámaras del Placer',
        'description': 'Supervisar la discreción y el descanso de las concubinas y favoritas del sultán.',
        'duration_minutes': 60,
        'gold_reward': 290,
        'reward_gold': 290,
        'xp_reward': 160,
        'reward_xp': 160,
        'min_level': 2,
        'icon': 'fa-solid fa-shield-halved',
        'emoji': '🪭',
        'badge_color': 'bg-purple-900/60 text-purple-300 border-purple-700/50',
    },
    {
        'id': 'noble_night_escort',
        'key': 'noble_night_escort',
        'role_type': 'cliente',
        'role_label': 'Noble / Cliente',
        'title': 'Escolta Íntima al Palacio Lunar',
        'description': 'Acompañar discretamente a una dama de alto rango a su encuentro secreto a la luz de las velas.',
        'duration_minutes': 120,
        'gold_reward': 650,
        'reward_gold': 650,
        'xp_reward': 350,
        'reward_xp': 350,
        'min_level': 3,
        'icon': 'fa-solid fa-moon',
        'emoji': '🌙',
        'badge_color': 'bg-indigo-900/60 text-indigo-300 border-indigo-700/50',
    },
    {
        'id': 'noble_pleasure_patron',
        'key': 'noble_pleasure_patron',
        'role_type': 'cliente',
        'role_label': 'Noble / Cliente',
        'title': 'Mecenas de la Fiesta de Baco',
        'description': 'Financiar y supervisar una bacanal real con las personalidades más extravagantes de la corte.',
        'duration_minutes': 240,
        'gold_reward': 1450,
        'reward_gold': 1450,
        'xp_reward': 800,
        'reward_xp': 800,
        'min_level': 4,
        'icon': 'fa-solid fa-crown',
        'emoji': '👑',
        'badge_color': 'bg-amber-900/60 text-amber-300 border-amber-700/50',
    },
    # --- LABORES EXCLUSIVAS PARA IDOLS / MUSAS ---
    {
        'id': 'idol_perfume_silk',
        'key': 'idol_perfume_silk',
        'role_type': 'idol',
        'role_label': 'Idol / Musa',
        'title': 'Perfumado de Velos y Almohadas',
        'description': 'Rociar mirra y rosas en los lechos reales dejando un rastro embriagador.',
        'duration_minutes': 15,
        'gold_reward': 65,
        'reward_gold': 65,
        'xp_reward': 35,
        'reward_xp': 35,
        'min_level': 1,
        'icon': 'fa-solid fa-spray-can-sparkles',
        'emoji': '🌸',
        'badge_color': 'bg-fuchsia-900/60 text-fuchsia-300 border-fuchsia-700/50',
    },
    {
        'id': 'idol_whisper_secrets',
        'key': 'idol_whisper_secrets',
        'role_type': 'idol',
        'role_label': 'Idol / Musa',
        'title': 'Confesiones y Susurros al Oído',
        'description': 'Entretener a clientes de alta alcurnia con secretos velados y halagos irresistibles.',
        'duration_minutes': 30,
        'gold_reward': 150,
        'reward_gold': 150,
        'xp_reward': 80,
        'reward_xp': 80,
        'min_level': 1,
        'icon': 'fa-solid fa-comment-dots',
        'emoji': '🤫',
        'badge_color': 'bg-pink-900/60 text-pink-300 border-pink-700/50',
    },
    {
        'id': 'idol_dance_seven_veils',
        'key': 'idol_dance_seven_veils',
        'role_type': 'idol',
        'role_label': 'Idol / Musa',
        'title': 'Danza de los Siete Velos',
        'description': 'Hechizar al salón principal con movimientos hipnóticos de cadera al son de címbalos.',
        'duration_minutes': 60,
        'gold_reward': 330,
        'reward_gold': 330,
        'xp_reward': 180,
        'reward_xp': 180,
        'min_level': 2,
        'icon': 'fa-solid fa-gem',
        'emoji': '💃',
        'badge_color': 'bg-rose-900/60 text-rose-300 border-rose-700/50',
    },
    {
        'id': 'idol_private_audience',
        'key': 'idol_private_audience',
        'role_type': 'idol',
        'role_label': 'Idol / Musa',
        'title': 'Audiencia Privada en la Torre de Marfil',
        'description': 'Una sesión exclusiva de masajes, licores y caricias para el benefactor más influyente.',
        'duration_minutes': 120,
        'gold_reward': 720,
        'reward_gold': 720,
        'xp_reward': 380,
        'reward_xp': 380,
        'min_level': 3,
        'icon': 'fa-solid fa-masks-theater',
        'emoji': '🫦',
        'badge_color': 'bg-violet-900/60 text-violet-300 border-violet-700/50',
    },
    {
        'id': 'idol_reina_noche',
        'key': 'idol_reina_noche',
        'role_type': 'idol',
        'role_label': 'Idol / Musa',
        'title': 'Soberana del Harén por una Noche',
        'description': 'Presidir el festival supremo del placer, recibiendo reverencias y cofres de oro puro.',
        'duration_minutes': 240,
        'gold_reward': 1600,
        'reward_gold': 1600,
        'xp_reward': 850,
        'reward_xp': 850,
        'min_level': 4,
        'icon': 'fa-solid fa-wand-magic-sparkles',
        'emoji': '✨',
        'badge_color': 'bg-amber-900/60 text-amber-300 border-amber-700/50',
    },
]


def court_jobs_view(request):
    """Vista principal blindada contra 500 para consultar y reclamar Labores de la Corte con distinción de roles."""
    try:
        tg_id = get_safe_tg_id(request)
        profile = None
        wallet = None

        if tg_id:
            try:
                profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            except Exception:
                profile = None

            try:
                wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
            except Exception:
                wallet = None

        # Identificar rol de forma 100% segura (UserRole o IdolProfile)
        is_idol = False
        if tg_id:
            try:
                role_obj = None
                try:
                    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
                except Exception:
                    try:
                        role_obj = UserRole.objects.filter(telegram_user_id=tg_id).first()
                    except Exception:
                        role_obj = None

                if role_obj and getattr(role_obj, 'role', '') == 'idol':
                    is_idol = True
                else:
                    try:
                        is_idol = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
                    except Exception:
                        is_idol = False
            except Exception:
                is_idol = False

        user_role_type = 'idol' if is_idol else 'cliente'
        role_jobs = [j for j in JOBS_CATALOG if j['role_type'] == user_role_type]
        other_jobs = [j for j in JOBS_CATALOG if j['role_type'] != user_role_type]

        active_job = None
        is_completed = False
        time_remaining_seconds = 0

        if tg_id:
            try:
                active_job = CourtJob.objects.filter(
                    telegram_user_id=tg_id,
                    is_claimed=False
                ).order_by('-created_at').first()
            except Exception:
                try:
                    active_job = CourtJob.objects.filter(
                        telegram_user_id=tg_id,
                        is_claimed=False
                    ).first()
                except Exception:
                    active_job = None

            if active_job:
                try:
                    now = timezone.now()
                    finishes = getattr(active_job, 'finishes_at', None)
                    if finishes:
                        if timezone.is_naive(finishes):
                            finishes = timezone.make_aware(finishes)
                        if now >= finishes:
                            is_completed = True
                            time_remaining_seconds = 0
                        else:
                            is_completed = False
                            time_remaining_seconds = max(0, int((finishes - now).total_seconds()))
                    else:
                        is_completed = True
                        time_remaining_seconds = 0
                except Exception:
                    try:
                        is_completed = active_job.is_finished()
                        time_remaining_seconds = active_job.seconds_remaining()
                    except Exception:
                        is_completed = False
                        time_remaining_seconds = 0

        context = {
            'tg_id': tg_id,
            'profile': profile,
            'wallet': wallet,
            'user_role_type': user_role_type,
            'is_idol': is_idol,
            'role_jobs': role_jobs,
            'other_jobs': other_jobs,
            'available_jobs': JOBS_CATALOG,
            'jobs': JOBS_CATALOG,
            'active_job': active_job,
            'is_completed': is_completed,
            'time_remaining_seconds': time_remaining_seconds,
        }
        return render(request, 'economy/jobs.html', context)
    except Exception as e:
        # Fallback a prueba de fallos: la página carga aún si la base de datos tuviera algún problema
        tg_id = get_safe_tg_id(request)
        messages.warning(request, f"Aviso de la Corte: {str(e)}")
        fallback_role_jobs = [j for j in JOBS_CATALOG if j['role_type'] == 'cliente']
        fallback_other_jobs = [j for j in JOBS_CATALOG if j['role_type'] == 'idol']
        return render(request, 'economy/jobs.html', {
            'tg_id': tg_id,
            'profile': None,
            'wallet': None,
            'user_role_type': 'cliente',
            'is_idol': False,
            'role_jobs': fallback_role_jobs,
            'other_jobs': fallback_other_jobs,
            'available_jobs': JOBS_CATALOG,
            'jobs': JOBS_CATALOG,
            'active_job': None,
            'is_completed': False,
            'time_remaining_seconds': 0,
        })


@require_POST
def start_court_job(request):
    """Inicia una nueva labor de la corte si no hay otra en curso."""
    tg_id = get_safe_tg_id(request)
    if not tg_id:
        messages.error(request, 'Sesión no válida.')
        return redirect('economy:jobs')

    job_key = request.POST.get('job_key') or request.POST.get('job_id')

    try:
        existing = CourtJob.objects.filter(
            telegram_user_id=tg_id,
            is_claimed=False
        ).first()
        if existing:
            messages.warning(request, 'Ya tienes una labor en curso en la corte.')
            return redirect(f'/economy/jobs/?tg_id={tg_id}')
    except Exception:
        messages.error(request, 'Error al consultar la labor activa. Asegúrate de haber ejecutado las migraciones.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    matched = next((j for j in JOBS_CATALOG if j['id'] == job_key or j['key'] == job_key), None)
    if not matched:
        messages.error(request, 'La labor seleccionada no existe.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    profile = None
    try:
        profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
    except Exception:
        profile = None
    user_level = profile.level if profile and hasattr(profile, 'level') else 1

    if user_level < matched.get('min_level', 1):
        messages.error(request, f"Requiere nivel {matched['min_level']} en la corte.")
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    finishes = timezone.now() + timedelta(minutes=matched['duration_minutes'])
    try:
        CourtJob.objects.create(
            telegram_user_id=tg_id,
            job_key=matched['id'],
            title=matched['title'],
            role_type=matched.get('role_type', 'cliente'),
            gold_reward=matched['gold_reward'],
            xp_reward=matched['xp_reward'],
            duration_minutes=matched['duration_minutes'],
            finishes_at=finishes,
            is_claimed=False
        )
        messages.success(request, f'¡Has iniciado la labor: "{matched["title"]}"!')
    except Exception as e:
        messages.error(request, f'Error al iniciar labor: {str(e)}')
    return redirect(f'/economy/jobs/?tg_id={tg_id}')


@require_POST
def claim_court_job(request):
    """Reclama la recompensa de una labor completada acreditando a Wallet y UserProfile."""
    tg_id = get_safe_tg_id(request)
    if not tg_id:
        messages.error(request, 'Sesión no válida.')
        return redirect('economy:jobs')

    job = None
    try:
        job = CourtJob.objects.filter(
            telegram_user_id=tg_id,
            is_claimed=False
        ).order_by('-created_at').first()
    except Exception:
        try:
            job = CourtJob.objects.filter(
                telegram_user_id=tg_id,
                is_claimed=False
            ).first()
        except Exception:
            job = None

    if not job:
        messages.warning(request, 'No tienes ninguna labor para reclamar.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    now = timezone.now()
    finishes = getattr(job, 'finishes_at', None)
    if finishes and timezone.is_naive(finishes):
        finishes = timezone.make_aware(finishes)

    if finishes and now < finishes:
        messages.error(request, 'Esta labor aún no ha finalizado.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    # 🪙 1. Acreditación de Oro
    try:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        if hasattr(wallet, 'add_funds'):
            wallet.add_funds(job.gold_reward)
        else:
            wallet.balance += job.gold_reward
            wallet.save()
    except Exception as e:
        messages.error(request, f'Error al acreditar oro: {str(e)}')

    # ✨ 2. Acreditación de XP
    try:
        grant_user_xp(request, tg_id, job.xp_reward, reason=f"Labor de la Corte: {job.title}")
    except Exception:
        try:
            profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            if profile and hasattr(profile, 'xp'):
                profile.xp += job.xp_reward
                profile.save()
        except Exception:
            pass

    # 3. Marcar como cobrada
    try:
        job.is_claimed = True
        job.save()
        messages.success(request, f'✨ ¡Tributo reclamado! +{job.gold_reward} Oro acreditados a tu Bóveda y +{job.xp_reward} EXP.')
    except Exception as e:
        messages.error(request, f'Error al actualizar labor: {str(e)}')

    return redirect(f'/economy/jobs/?tg_id={tg_id}')


# Alias de compatibilidad total
start_court_job_action = start_court_job
claim_court_job_action = claim_court_job


# ==============================================================================
# 💎 BOUTIQUE REAL: COLECCIONABLES CON FOTOS
# ==============================================================================
def buy_collectible_action(request, item_id):
    if request.method != 'POST':
        return redirect('/economy/bazar/')
        
    tg_id = get_safe_tg_id(request)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
    item = get_object_or_404(BazarCollectible, id=item_id, is_active=True)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    if not item.is_in_stock:
        err = "Este artículo exclusivo se encuentra agotado."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    if wallet.balance < item.price:
        err = f"Oro insuficiente ({wallet.balance}/{item.price} 🪙)."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    with transaction.atomic():
        wallet.remove_funds(item.price)
        if item.stock > 0:
            item.stock -= 1
            item.save(update_fields=['stock'])
        uc, created = UserCollectible.objects.get_or_create(telegram_user_id=tg_id, item=item)
        if not created:
            uc.quantity += 1
            uc.save(update_fields=['quantity'])

    grant_user_xp(request, tg_id, max(10, item.price // 15), reason=f"Colección Boutique: {item.name}")
    msg = f"👑 ¡Has adquirido la reliquia «{item.name}»! Ahora reposa en tu vitrina de honor."
    if is_ajax:
        return JsonResponse({'success': True, 'message': msg, 'nuevo_saldo': wallet.balance})
    messages.success(request, msg)
    return redirect(f'/economy/bazar/?tg_id={tg_id}')

def admin_add_collectible(request):
    tg_id = get_safe_tg_id(request)
    if not check_is_staff_or_admin(tg_id):
        messages.error(request, "No posees la investidura imperial para modificar la Boutique.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price = int(request.POST.get('price', 100))
        stock = int(request.POST.get('stock', 10))
        image_file = request.FILES.get('image')

        if not name:
            messages.error(request, "El nombre del coleccionable es obligatorio.")
            return redirect(f'/economy/bazar/?tg_id={tg_id}')

        optimized = optimize_uploaded_image(image_file) if image_file else None

        BazarCollectible.objects.create(
            name=name,
            description=description,
            price=max(1, price),
            stock=max(1, stock),
            image=optimized
        )
        messages.success(request, f"✨ La reliquia «{name}» fue exhibida en la Boutique Real.")

    return redirect(f'/economy/bazar/?tg_id={tg_id}')


def admin_delete_collectible(request, item_id):
    tg_id = get_safe_tg_id(request)
    if not check_is_staff_or_admin(tg_id):
        messages.error(request, "Acción denegada por decreto real.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    item = get_object_or_404(BazarCollectible, id=item_id)
    item.is_active = False
    item.save()
    messages.info(request, f"El artículo «{item.name}» ha sido retirado de los estantes de la Boutique.")
    return redirect(f'/economy/bazar/?tg_id={tg_id}')

def admin_create_series_batch(request):
    """Crea una colección Pop Mart completa con múltiples figuras de golpe."""
    tg_id = get_safe_tg_id(request)
    if not check_is_staff_or_admin(tg_id):
        messages.error(request, "Acceso exclusivo para la corte de administración.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    if request.method == 'POST':
        from .models import CollectibleSeries
        series_name = request.POST.get('series_name', '').strip()
        tagline = request.POST.get('tagline', 'Pop Mart Series').strip()
        description = request.POST.get('description', '').strip()
        blind_price = int(request.POST.get('blind_box_price', 160))
        single_price = int(request.POST.get('single_price', 260))
        cover_file = request.FILES.get('cover_image')

        if not series_name:
            messages.error(request, "El nombre de la colección es requerido.")
            return redirect(f'/economy/bazar/?tg_id={tg_id}')

        optimized_cover = optimize_uploaded_image(cover_file) if cover_file else None

        with transaction.atomic():
            series = CollectibleSeries.objects.create(
                name=series_name,
                tagline=tagline,
                description=description,
                cover_image=optimized_cover,
                blind_box_price=max(10, blind_price),
                single_price=max(10, single_price)
            )

            # Recorrer todas las figuras subidas en lote
            figure_images = request.FILES.getlist('figures')
            figure_names = request.POST.getlist('figure_names')
            secret_indices = request.POST.getlist('is_secret_index')

            for idx, img in enumerate(figure_images):
                opt_img = optimize_uploaded_image(img)
                fig_name = figure_names[idx].strip() if idx < len(figure_names) and figure_names[idx].strip() else f"{series_name} #{idx+1}"
                is_sec = str(idx) in secret_indices

                BazarCollectible.objects.create(
                    series=series,
                    name=fig_name,
                    category='figura',
                    price=single_price,
                    image=opt_img,
                    stock=-1,
                    is_secret=is_sec,
                    idol_name=fig_name
                )

        messages.success(request, f"✨ ¡Colección «{series_name}» publicada con éxito ({len(figure_images)} figuras)!")
    return redirect(f'/economy/bazar/?tg_id={tg_id}')

def buy_blind_box_action(request, series_id):
    """Mecánica Blind Box: adquiere una figura aleatoria de la colección."""
    if request.method != 'POST':
        return redirect('/economy/bazar/')

    tg_id = get_safe_tg_id(request)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'

    from .models import CollectibleSeries
    series = get_object_or_404(CollectibleSeries, id=series_id, is_active=True)
    available_items = list(series.items.filter(is_active=True))

    if not available_items:
        err = "Esta colección aún no tiene figuras disponibles."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    if wallet.balance < series.blind_box_price:
        err = f"Oro insuficiente para la Caja Sorpresa ({wallet.balance}/{series.blind_box_price} 🪙)."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/economy/bazar/?tg_id={tg_id}')

    # Ponderación: las secretas tienen 5% de probabilidad, las regulares 95%
    secrets = [it for it in available_items if it.is_secret]
    regulars = [it for it in available_items if not it.is_secret]

    if secrets and random.random() < 0.05:
        chosen_item = random.choice(secrets)
    else:
        chosen_item = random.choice(regulars) if regulars else random.choice(available_items)

    with transaction.atomic():
        wallet.remove_funds(series.blind_box_price)
        uc, created = UserCollectible.objects.get_or_create(telegram_user_id=tg_id, item=chosen_item)
        if not created:
            uc.quantity += 1
            uc.save(update_fields=['quantity'])

    grant_user_xp(request, tg_id, 20, reason=f"Blind Box: {series.name}")

    msg = f"🎉 ¡Has abierto una Caja Sorpresa de {series.name} y obtuviste a «{chosen_item.name}»!"
    if chosen_item.is_secret:
        msg = f"⭐👑 ¡FIESTA REAL! ¡Has desenterrado la FIGURA SECRETA: «{chosen_item.name}»!"

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': msg,
            'figure_name': chosen_item.name,
            'figure_image': chosen_item.image.url if chosen_item.image else '',
            'is_secret': chosen_item.is_secret,
            'nuevo_saldo': wallet.balance
        })

    messages.success(request, msg)
    return redirect(f'/economy/bazar/?tg_id={tg_id}')

# ==============================================================================
# 🎫 RASPA Y GANA IMPERIAL (SCRATCH CARDS)
# ==============================================================================
SCRATCH_TIERS = {
    'bronze': {
        'name': 'Cartón de Bronce Clandestino',
        'cost': 25,
        'badge': 'bg-amber-900/60 text-amber-300 border-amber-700/50',
        'max_prize': 250,
        'desc': 'Para iniciados y curiosos. Premios modestos pero frecuentes.',
        'accent': 'from-amber-900/30 to-amber-950/50 border-amber-500/30'
    },
    'silver': {
        'name': 'Cartón de Plata Espectral',
        'cost': 60,
        'badge': 'bg-neutral-800 text-neutral-200 border-neutral-600',
        'max_prize': 650,
        'desc': 'Para caballeros y damas audaces. Mayor retorno y gemas ocultas.',
        'accent': 'from-neutral-800/40 to-neutral-900 border-neutral-500/40'
    },
    'gold': {
        'name': 'Cartón de Oro Imperial',
        'cost': 150,
        'badge': 'bg-yellow-900/60 text-yellow-300 border-yellow-600/60',
        'max_prize': 2000,
        'desc': 'Para duques y soberanos. Jackpots de oro puro y honores dinásticos.',
        'accent': 'from-yellow-950/40 to-amber-900/30 border-yellow-500/40'
    }
}

SCRATCH_SYMBOLS = {
    'grape': {'symbol': '🍇', 'name': 'Uvas Prohibidas', 'mult': 2, 'weight': 38},
    'cherry': {'symbol': '🍒', 'name': 'Cerezas del Placer', 'mult': 3, 'weight': 28},
    'coin': {'symbol': '🪙', 'name': 'Moneda Real', 'mult': 5, 'weight': 18},
    'star': {'symbol': '⭐', 'name': 'Estrella de Venus', 'mult': 8, 'weight': 10},
    'diamond': {'symbol': '💎', 'name': 'Diamante Imperial', 'mult': 15, 'weight': 5},
    'crown': {'symbol': '👑', 'name': 'Corona Soberana', 'mult': 35, 'weight': 1},
}


def scratch_card_view(request):
    """Renderiza la vista principal de Raspa y Gana."""
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)

    return render(request, 'economy/scratch.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'tiers': SCRATCH_TIERS,
    })


def scratch_card_play_ajax(request):
    """Compra y genera la cuadrícula 3x3 del cartón vía AJAX con Pity System calibrado."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    tg_id = get_safe_tg_id(request)
    tier_key = request.POST.get('tier', 'bronze').strip().lower()

    if tier_key not in SCRATCH_TIERS:
        return JsonResponse({'success': False, 'error': 'Cartón no válido.'}, status=400)

    tier = SCRATCH_TIERS[tier_key]
    cost = tier['cost']

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)

    if wallet.balance < cost:
        return JsonResponse({
            'success': False,
            'error': f'Oro insuficiente. El cartón cuesta {cost} 🪙 y posees {wallet.balance} 🪙.'
        }, status=400)

    # Colores visuales para cada símbolo en el cartón
    symbol_colors = {
        'grape': '#a855f7',
        'cherry': '#f43f5e',
        'coin': '#eab308',
        'star': '#fbbf24',
        'diamond': '#38bdf8',
        'crown': '#f59e0b',
    }

    with transaction.atomic():
        # Cobrar cartón y alimentar Cofre del Mecenas (8%)
        wallet.remove_funds(cost)
        wallet.accumulate_patron_vault(cost)
        balance_after_cost = wallet.balance

        # Sistema de Pity
        consecutive_losses = request.session.get("scratch_consecutive_losses", 0)
        win_chance = min(0.75, 0.35 + (consecutive_losses * 0.10))
        is_win = random.random() < win_chance

        if is_win:
            request.session["scratch_consecutive_losses"] = 0
        else:
            request.session["scratch_consecutive_losses"] = consecutive_losses + 1

        symbols_keys = list(SCRATCH_SYMBOLS.keys())
        weights = [SCRATCH_SYMBOLS[k]["weight"] for k in symbols_keys]
        winning_key = None

        serial_code = f"{random.randint(100000, 999999)}"

        if is_win:
            winning_key = random.choices(symbols_keys, weights=weights, k=1)[0]
            winning_mult = SCRATCH_SYMBOLS[winning_key]['mult']
            win_amount = cost * winning_mult

            # Bonificación de Mascota Pantera
            try:
                pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                if pet and pet.species == 'panther':
                    rates = {1: 0.05, 2: 0.10, 3: 0.18}
                    bonus_factor = rates.get(pet.evolution_stage_number, 0.05)
                    net_gain = max(0, win_amount - cost)
                    win_amount = int(cost + (net_gain * (1 + bonus_factor)))
            except Exception:
                pass

            wallet.add_funds(win_amount)
            grant_user_xp(request, tg_id, max(4, win_amount // 25), reason="Victoria en Raspa y Gana")

            # Construir la cuadrícula 3x3 garantizando exactamente 3 símbolos ganadores
            winning_positions = random.sample(range(9), 3)
            grid = [None] * 9
            for pos in winning_positions:
                grid[pos] = winning_key

            other_keys = [k for k in symbols_keys if k != winning_key]
            counts = {k: 0 for k in other_keys}
            for i in range(9):
                if grid[i] is None:
                    avail = [k for k in other_keys if counts[k] < 2]
                    chosen = random.choice(avail) if avail else random.choice(other_keys)
                    grid[i] = chosen
                    counts[chosen] = counts.get(chosen, 0) + 1

            cells = [{
                'symbol': SCRATCH_SYMBOLS[k]['symbol'],
                'name': SCRATCH_SYMBOLS[k]['name'],
                'color': symbol_colors.get(k, '#fbbf24'),
                'key': k,
                'is_winner': (k == winning_key)
            } for k in grid]

            return JsonResponse({
                'success': True,
                'is_win': True,
                'win_amount': win_amount,
                'payout': win_amount,
                'winning_symbol': SCRATCH_SYMBOLS[winning_key]['symbol'],
                'winning_name': SCRATCH_SYMBOLS[winning_key]['name'],
                'winning_mult': SCRATCH_SYMBOLS[winning_key]['mult'],
                'grid': cells,
                'cells': cells,
                'serial': serial_code,
                'balance_after_cost': balance_after_cost,
                'new_balance': wallet.balance,
                'patron_vault': wallet.patron_vault,
                'message': f'🎉 ¡Enhorabuena! Has alineado 3 {SCRATCH_SYMBOLS[winning_key]["symbol"]} y cobrado +{win_amount} 🪙.'
            })

        else:
            grant_user_xp(request, tg_id, 1, reason="Participación en Raspa y Gana")

            grid = []
            counts = {k: 0 for k in symbols_keys}
            for _ in range(9):
                avail = [k for k in symbols_keys if counts[k] < 2]
                chosen = random.choice(avail) if avail else random.choice(symbols_keys)
                grid.append(chosen)
                counts[chosen] = counts.get(chosen, 0) + 1

            cells = [{
                'symbol': SCRATCH_SYMBOLS[k]['symbol'],
                'name': SCRATCH_SYMBOLS[k]['name'],
                'color': symbol_colors.get(k, '#fbbf24'),
                'key': k,
                'is_winner': False
            } for k in grid]

            return JsonResponse({
                'success': True,
                'is_win': False,
                'win_amount': 0,
                'payout': 0,
                'grid': cells,
                'cells': cells,
                'serial': serial_code,
                'balance_after_cost': balance_after_cost,
                'new_balance': wallet.balance,
                'patron_vault': wallet.patron_vault,
                'message': f'💀 Sin suerte esta vez. Tu cartón no obtuvo trío. El 8% ({int(round(cost * 0.08))} 🪙) pasó a tu Cofre del Mecenas.'
            })