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
    Wallet,
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
        'can_claim_bonus': wallet.can_claim_bonus(),
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
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
    
    # 👑 ESCALADO DE APUESTA MÁXIMA SEGÚN RANGO / ROL
    base_max = 500
    if profile.level >= 10:
        base_max = 2000
    elif profile.level >= 5:
        base_max = 1000

    if profile.role:
        role_maxes = {
            'plebeyo': 500,
            'noble': 1500,
            'vizconde': 3000,
            'conde': 6000,
            'marques': 12000,
            'duque': 25000,
            'rey': 50000,
            'emperador': 100000,
            'corona': 250000,
        }
        role_key = profile.role.name.lower()
        base_max = max(base_max, role_maxes.get(role_key, 500))

    max_bet = base_max

    if request.method == 'POST':
        bet_type = request.POST.get('bet_type')
        bet_value = request.POST.get('bet_value')
        
        try:
            bet_amount = int(request.POST.get('bet_amount', 0))
        except (ValueError, TypeError):
            bet_amount = 0
            
        if bet_amount <= 0:
            err = "Debes ingresar una cantidad válida de oro para apostar."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/casino/?tg_id={tg_id}')
            
        if bet_amount > max_bet:
            err = f"Tu estatus nobiliario solo te permite apostar un máximo de {max_bet} 🪙 por giro."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/casino/?tg_id={tg_id}')
            
        if wallet.balance < bet_amount:
            err = "No tienes suficiente oro en tu billetera imperial."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/casino/?tg_id={tg_id}')
            
        # Cobro y Rakeback al Cofre del Mecenas (8%)
        wallet.remove_funds(bet_amount)
        rebate = wallet.accumulate_patron_vault(bet_amount)
        
        # 🎰 RULETA EUROPEA REAL (0 al 36)
        winning_number = random.randint(0, 36)
        
        # Definición oficial de Ruleta Francesa / Europea
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        if winning_number == 0:
            winning_color = 'green'
        elif winning_number in red_numbers:
            winning_color = 'red'
        else:
            winning_color = 'black'
            
        won = False
        payout_multiplier = 0
        
        if bet_type == 'color':
            if bet_value == winning_color and winning_color != 'green':
                won = True
                payout_multiplier = 2
        elif bet_type == 'parity':
            if winning_number != 0:
                is_even = (winning_number % 2 == 0)
                if (bet_value == 'even' and is_even) or (bet_value == 'odd' and not is_even):
                    won = True
                    payout_multiplier = 2
        elif bet_type == 'number':
            try:
                if int(bet_value) == winning_number:
                    won = True
                    payout_multiplier = 36
            except (ValueError, TypeError):
                pass
                
        payout = 0
        if won:
            payout = bet_amount * payout_multiplier
            wallet.add_funds(payout)
            # Recompensa de EXP nobiliaria
            xp_gain = max(2, bet_amount // 20)
            grant_user_xp(request, tg_id, xp_gain, reason="Ruleta Imperial")
            
            msg = f"🎉 ¡La diosa Fortuna te sonríe! La bola cayó en el {winning_number} ({winning_color.upper()}). ¡Ganaste +{payout} 🪙!"
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'won': True,
                    'winning_number': winning_number,
                    'winning_color': winning_color,
                    'payout': payout,
                    'net': payout - bet_amount,
                    'nuevo_saldo': wallet.balance,
                    'patron_vault': wallet.patron_vault,
                    'message': msg
                })
            messages.success(request, msg)
        else:
            msg = f"💀 La bola cayó en el {winning_number} ({winning_color.upper()}). Has perdido {bet_amount} 🪙. (+{rebate} 🪙 acumulados en tu Cofre de Mecenas)."
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'won': False,
                    'winning_number': winning_number,
                    'winning_color': winning_color,
                    'payout': 0,
                    'net': -bet_amount,
                    'nuevo_saldo': wallet.balance,
                    'patron_vault': wallet.patron_vault,
                    'message': msg
                })
            messages.warning(request, msg)
            
        return redirect(f'/economy/casino/?tg_id={tg_id}')
        
    return render(request, 'economy/casino.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
    })


def claim_bonus(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    if request.method == 'POST':
        if wallet.can_claim_bonus():
            base_bonus = 50
            
            # Bonificación por nivel del jugador (+10 de oro por nivel)
            level_bonus = (profile.level - 1) * 10
            total_bonus = base_bonus + level_bonus
            
            # BUFF KITSUNE CELESTIAL: Multiplicador de Recompensa Diaria
            try:
                pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                if pet and pet.species == 'kitsune':
                    mults = {1: 1.25, 2: 1.50, 3: 2.0}
                    kitsune_mult = mults.get(pet.evolution_stage_number, 1.25)
                    total_bonus = int(round(total_bonus * kitsune_mult))
            except Exception:
                pass
            
            wallet.add_funds(total_bonus)
            wallet.last_bonus_claim = timezone.now()
            wallet.save()
            
            grant_user_xp(request, tg_id, 25, reason="Ruleta de la Fortuna")
            messages.success(request, f"✨ ¡Has recibido tu ofrenda diaria de la Corte! +{total_bonus} 🪙 añadidos a tu billetera.")
        else:
            messages.error(request, "⏳ Aún no puedes reclamar tu estipendio diario. El ciclo se renueva puntualmente a las 12:00 PM.")
            
    return redirect(f'/economy/wallet/?tg_id={tg_id}')


# ==============================================================================
# 🎰 TRAGAPERRAS IMPERIAL (SLOTS REALES)
# ==============================================================================
SLOT_SYMBOLS = [
    {'name': 'Cereza', 'symbol': '🍒', 'mult': 3, 'weight': 38},
    {'name': 'Campana', 'symbol': '🔔', 'mult': 6, 'weight': 28},
    {'name': 'Herradura', 'symbol': '🍀', 'mult': 12, 'weight': 18},
    {'name': 'Rubí Real', 'symbol': '💎', 'mult': 25, 'weight': 10},
    {'name': 'Corona Imperial', 'symbol': '👑', 'mult': 60, 'weight': 5},
    {'name': 'Cofre del Placer', 'symbol': '7️⃣', 'mult': 150, 'weight': 1},
]

def slots_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
    
    max_bet = 500
    if profile.level >= 10:
        max_bet = 2000
    elif profile.level >= 5:
        max_bet = 1000

    if request.method == 'POST':
        try:
            bet_amount = int(request.POST.get('bet_amount', 10))
        except (ValueError, TypeError):
            bet_amount = 10
            
        if bet_amount <= 0:
            err = "Ingresa una apuesta válida de oro."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/slots/?tg_id={tg_id}')
            
        if bet_amount > max_bet:
            err = f"La apuesta máxima permitida para tu nivel es de {max_bet} 🪙."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/slots/?tg_id={tg_id}')

        if wallet.balance < bet_amount:
            err = "No tienes suficiente oro para activar los rodillos."
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/economy/slots/?tg_id={tg_id}')
            
        # Descontar apuesta y abonar al Cofre del Mecenas (8%)
        wallet.remove_funds(bet_amount)
        wallet.accumulate_patron_vault(bet_amount)
        
        # Tirada ponderada para 3 rodillos
        symbols_names = [s['name'] for s in SLOT_SYMBOLS]
        weights = [s['weight'] for s in SLOT_SYMBOLS]
        
        spin_result = random.choices(symbols_names, weights=weights, k=3)
        symbols_map = {s['name']: s for s in SLOT_SYMBOLS}
        
        reel1 = symbols_map[spin_result[0]]
        reel2 = symbols_map[spin_result[1]]
        reel3 = symbols_map[spin_result[2]]
        
        won = False
        payout = 0
        win_type = "loss"
        matched_symbol = None
        
        # Regla 1: Triple coincidencia (Jackpot del símbolo)
        if reel1['name'] == reel2['name'] == reel3['name']:
            won = True
            matched_symbol = reel1
            payout = bet_amount * matched_symbol['mult']
            win_type = "jackpot"
        # Regla 2: Doble coincidencia (Premio menor: 1.5x)
        elif reel1['name'] == reel2['name'] or reel2['name'] == reel3['name'] or reel1['name'] == reel3['name']:
            won = True
            payout = int(round(bet_amount * 1.5))
            win_type = "double"
            
        if won:
            wallet.add_funds(payout)
            xp_gain = max(2, bet_amount // 15)
            grant_user_xp(request, tg_id, xp_gain, reason="Tragaperras Imperial")
            
        if is_ajax:
            return JsonResponse({
                'success': True,
                'reels': [
                    {'name': reel1['name'], 'symbol': reel1['symbol']},
                    {'name': reel2['name'], 'symbol': reel2['symbol']},
                    {'name': reel3['name'], 'symbol': reel3['symbol']},
                ],
                'won': won,
                'win_type': win_type,
                'payout': payout,
                'net': payout - bet_amount,
                'nuevo_saldo': wallet.balance,
                'patron_vault': wallet.patron_vault,
            })
            
        if won:
            messages.success(request, f"🎰 ¡TRIPLE ORO! Los rodillos se alinearon. ¡Cobraste +{payout} 🪙!")
        else:
            messages.warning(request, f"🎰 Los rodillos se detuvieron sin suerte. Has perdido {bet_amount} 🪙.")
        return redirect(f'/economy/slots/?tg_id={tg_id}')
        
    return render(request, 'economy/slots.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'max_bet': max_bet,
        'symbols': SLOT_SYMBOLS,
    })


# ==============================================================================
# 💣 MINAS DEL REINO (MINES GAME)
# ==============================================================================
def calculate_mines_multiplier(total_mines, diamonds_found):
    """Calcula el multiplicador acumulativo con RTP del 94% garantizado"""
    if diamonds_found == 0:
        return 1.0
    safe_tiles = 25 - total_mines
    prob = 1.0
    for i in range(diamonds_found):
        prob *= (safe_tiles - i) / (25 - i)
    raw_mult = 0.94 / prob
    return round(raw_mult, 2)


def mines_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    session_key = f'mines_game_{tg_id}'
    game_state = request.session.get(session_key)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. INICIAR NUEVA PARTIDA
        if action == 'start':
            if game_state and game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'Ya tienes una partida de minas en curso.'}, status=400)
                
            try:
                bet_amount = int(request.POST.get('bet_amount', 10))
                mines_count = int(request.POST.get('mines_count', 3))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Valores no válidos.'}, status=400)
                
            if bet_amount <= 0 or bet_amount > wallet.balance:
                return JsonResponse({'success': False, 'error': 'Saldo insuficiente para iniciar.'}, status=400)
                
            if mines_count < 1 or mines_count > 24:
                return JsonResponse({'success': False, 'error': 'Número de minas fuera de rango (1 a 24).'}, status=400)
                
            # Cobro y Rakeback
            wallet.remove_funds(bet_amount)
            wallet.accumulate_patron_vault(bet_amount)
            
            # Generar posiciones aleatorias de minas (0 a 24)
            mines_positions = random.sample(range(25), mines_count)
            
            new_state = {
                'active': True,
                'bet_amount': bet_amount,
                'mines_count': mines_count,
                'mines_positions': mines_positions,
                'revealed_tiles': [],
                'diamonds_found': 0,
                'current_multiplier': 1.0,
            }
            request.session[session_key] = new_state
            
            return JsonResponse({
                'success': True,
                'active': True,
                'bet_amount': bet_amount,
                'mines_count': mines_count,
                'nuevo_saldo': wallet.balance,
                'patron_vault': wallet.patron_vault,
            })
            
        # 2. DESTAPAR CASILLA
        elif action == 'reveal':
            if not game_state or not game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'No hay ninguna partida activa.'}, status=400)
                
            try:
                tile_index = int(request.POST.get('tile_index'))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Casilla no válida.'}, status=400)
                
            if tile_index < 0 or tile_index > 24:
                return JsonResponse({'success': False, 'error': 'Índice de casilla incorrecto.'}, status=400)
                
            if tile_index in game_state['revealed_tiles']:
                return JsonResponse({'success': False, 'error': 'Esta casilla ya fue destapada.'}, status=400)
                
            # ¿Es una mina?
            if tile_index in game_state['mines_positions']:
                # BUFF DRAGÓN DE LAS PROFUNDIDADES: Resistencia o Escudo contra explosión (Opcional)
                game_state['active'] = False
                all_mines = game_state['mines_positions']
                bet = game_state['bet_amount']
                del request.session[session_key]
                request.session.modified = True
                
                grant_user_xp(request, tg_id, 1, reason="Minas del Reino")
                
                return JsonResponse({
                    'success': True,
                    'hit_mine': True,
                    'tile_index': tile_index,
                    'mines_positions': all_mines,
                    'lost_amount': bet,
                    'nuevo_saldo': wallet.balance,
                    'message': '💥 ¡BOOM! Has pisado una trampa imperial oculta. Has perdido tu apuesta.'
                })
            else:
                # Es un diamante
                game_state['revealed_tiles'].append(tile_index)
                game_state['diamonds_found'] += 1
                new_mult = calculate_mines_multiplier(game_state['mines_count'], game_state['diamonds_found'])
                
                # BUFF DRAGÓN FÉNIX: Multiplicador adicional
                try:
                    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                    if pet and pet.species == 'dragon':
                        dragon_bonus = {1: 1.05, 2: 1.10, 3: 1.20}.get(pet.evolution_stage_number, 1.05)
                        new_mult = round(new_mult * dragon_bonus, 2)
                except Exception:
                    pass

                game_state['current_multiplier'] = new_mult
                current_payout = int(round(game_state['bet_amount'] * new_mult))
                request.session[session_key] = game_state
                request.session.modified = True
                
                # Si destapó todos los diamantes posibles, gana automáticamente
                total_safe = 25 - game_state['mines_count']
                all_cleared = (game_state['diamonds_found'] == total_safe)
                
                if all_cleared:
                    wallet.add_funds(current_payout)
                    del request.session[session_key]
                    grant_user_xp(request, tg_id, 8, reason="Pleno en Minas")
                    return JsonResponse({
                        'success': True,
                        'hit_mine': False,
                        'all_cleared': True,
                        'tile_index': tile_index,
                        'diamonds_found': game_state['diamonds_found'],
                        'multiplier': new_mult,
                        'current_payout': current_payout,
                        'nuevo_saldo': wallet.balance,
                        'message': f"👑 ¡INCREÍBLE! ¡Has destapado todos los diamantes! Cobraste +{current_payout} 🪙."
                    })
                    
                return JsonResponse({
                    'success': True,
                    'hit_mine': False,
                    'tile_index': tile_index,
                    'diamonds_found': game_state['diamonds_found'],
                    'multiplier': new_mult,
                    'current_payout': current_payout,
                })
                
        # 3. RETIRARSE Y COBRAR (CASH OUT)
        elif action == 'cashout':
            if not game_state or not game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'No hay partida activa para cobrar.'}, status=400)
                
            if game_state['diamonds_found'] == 0:
                return JsonResponse({'success': False, 'error': 'Debes revelar al menos un diamante antes de cobrar.'}, status=400)
                
            final_payout = int(round(game_state['bet_amount'] * game_state['current_multiplier']))
            wallet.add_funds(final_payout)
            
            all_mines = game_state['mines_positions']
            del request.session[session_key]
            request.session.modified = True
            
            grant_user_xp(request, tg_id, 3, reason="Retiro de Minas")
            
            return JsonResponse({
                'success': True,
                'cashed_out': True,
                'payout': final_payout,
                'multiplier': game_state['current_multiplier'],
                'mines_positions': all_mines,
                'nuevo_saldo': wallet.balance,
                'message': f"🏆 ¡Retirada victoriosa! Has asegurado +{final_payout} 🪙 a tu bóveda."
            })
            
        return JsonResponse({'success': False, 'error': 'Acción desconocida'}, status=400)
        
    return render(request, 'economy/mines.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'game_state': game_state,
    })


# ==============================================================================
# 🃏 BLACKJACK DE LA CORTE (21 REAL)
# ==============================================================================
DECK_SUITS = ['♠️', '♥️', '♦️', '♣️']
DECK_VALUES = [
    ('2', 2), ('3', 3), ('4', 4), ('5', 5), ('6', 6), ('7', 7),
    ('8', 8), ('9', 9), ('10', 10), ('J', 10), ('Q', 10), ('K', 10), ('A', 11)
]

def draw_card():
    val_name, val_points = random.choice(DECK_VALUES)
    suit = random.choice(DECK_SUITS)
    is_red = suit in ['♥️', '♦️']
    return {
        'name': val_name,
        'points': val_points,
        'suit': suit,
        'is_red': is_red,
        'display': f"{val_name}{suit}"
    }

def calculate_hand_value(hand):
    total = sum(c['points'] for c in hand)
    aces = sum(1 for c in hand if c['name'] == 'A')
    # Ajustar ases de 11 a 1 si nos pasamos de 21
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def blackjack_game(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    session_key = f'bj_game_{tg_id}'
    game_state = request.session.get(session_key)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. EMPEZAR PARTIDA
        if action == 'deal':
            if game_state and game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'Termina tu mano actual antes de repartir otra.'}, status=400)
                
            try:
                bet_amount = int(request.POST.get('bet_amount', 25))
            except (ValueError, TypeError):
                bet_amount = 25
                
            if bet_amount <= 0 or bet_amount > wallet.balance:
                return JsonResponse({'success': False, 'error': 'Oro insuficiente para la apuesta.'}, status=400)
                
            wallet.remove_funds(bet_amount)
            wallet.accumulate_patron_vault(bet_amount)
            
            player_hand = [draw_card(), draw_card()]
            dealer_hand = [draw_card(), draw_card()]
            
            p_score = calculate_hand_value(player_hand)
            d_score = calculate_hand_value(dealer_hand)
            
            # Blackjack natural directo del jugador
            if p_score == 21:
                # Si dealer también tiene 21 -> Empate
                if d_score == 21:
                    wallet.add_funds(bet_amount)
                    msg = "⚔️ ¡Empate imperial de Blackjacks! Se devuelve tu apuesta íntegra."
                    payout = bet_amount
                else:
                    payout = int(round(bet_amount * 2.5))  # Paga 3:2 clásico
                    wallet.add_funds(payout)
                    msg = f"👑 ¡BLACKJACK REAL! Has obtenido 21 directo. Cobras +{payout} 🪙."
                    grant_user_xp(request, tg_id, max(4, bet_amount // 10), reason="Blackjack")
                    
                return JsonResponse({
                    'success': True,
                    'game_over': True,
                    'player_hand': player_hand,
                    'dealer_hand': dealer_hand,
                    'player_score': 21,
                    'dealer_score': d_score,
                    'payout': payout,
                    'nuevo_saldo': wallet.balance,
                    'patron_vault': wallet.patron_vault,
                    'message': msg
                })
                
            # Estado en juego
            new_state = {
                'active': True,
                'bet_amount': bet_amount,
                'player_hand': player_hand,
                'dealer_hand': dealer_hand,
            }
            request.session[session_key] = new_state
            
            return JsonResponse({
                'success': True,
                'game_over': False,
                'player_hand': player_hand,
                'dealer_upcard': dealer_hand[0],  # Solo la primera carta visible
                'player_score': p_score,
                'nuevo_saldo': wallet.balance,
                'patron_vault': wallet.patron_vault,
            })
            
        # 2. PEDIR CARTA (HIT)
        elif action == 'hit':
            if not game_state or not game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'No hay partida activa.'}, status=400)
                
            card = draw_card()
            game_state['player_hand'].append(card)
            p_score = calculate_hand_value(game_state['player_hand'])
            
            # Comprobar si se pasó de 21
            if p_score > 21:
                # BUFF LOBO ESPECTRAL: Salvamento de bust (Opcional)
                game_state['active'] = False
                bet = game_state['bet_amount']
                dealer_hand = game_state['dealer_hand']
                del request.session[session_key]
                request.session.modified = True
                
                grant_user_xp(request, tg_id, 1, reason="Derrota Blackjack")
                
                return JsonResponse({
                    'success': True,
                    'game_over': True,
                    'busted': True,
                    'player_hand': game_state['player_hand'],
                    'dealer_hand': dealer_hand,
                    'player_score': p_score,
                    'dealer_score': calculate_hand_value(dealer_hand),
                    'payout': 0,
                    'nuevo_saldo': wallet.balance,
                    'message': f"💀 Te has pasado con {p_score}. El croupier gana la ronda."
                })
                
            request.session[session_key] = game_state
            request.session.modified = True
            
            return JsonResponse({
                'success': True,
                'game_over': False,
                'card_drawn': card,
                'player_hand': game_state['player_hand'],
                'player_score': p_score,
            })
            
        # 3. PLANTARSE (STAND)
        elif action == 'stand':
            if not game_state or not game_state.get('active'):
                return JsonResponse({'success': False, 'error': 'No hay partida activa.'}, status=400)
                
            player_hand = game_state['player_hand']
            dealer_hand = game_state['dealer_hand']
            bet = game_state['bet_amount']
            
            p_score = calculate_hand_value(player_hand)
            d_score = calculate_hand_value(dealer_hand)
            
            # El croupier debe pedir carta obligatoriamente hasta alcanzar 17 o más
            while d_score < 17:
                dealer_hand.append(draw_card())
                d_score = calculate_hand_value(dealer_hand)
                
            won = False
            is_push = False
            payout = 0
            
            if d_score > 21:
                # Crupier se pasó -> Gana jugador
                won = True
                payout = bet * 2
                msg = f"🎉 ¡El croupier se pasó con {d_score}! Has ganado +{payout} 🪙."
            elif p_score > d_score:
                won = True
                payout = bet * 2
                msg = f"⚔️ ¡Tu mano ({p_score}) supera a la del croupier ({d_score})! Ganas +{payout} 🪙."
            elif p_score == d_score:
                is_push = True
                payout = bet
                msg = f"🛡️ Empate a {p_score}. Tu apuesta de {bet} 🪙 queda a salvo."
            else:
                msg = f"💀 La banca gana con {d_score} frente a tu {p_score}."
                
            if payout > 0:
                wallet.add_funds(payout)
                
            del request.session[session_key]
            request.session.modified = True
            
            if won:
                grant_user_xp(request, tg_id, 4, reason="Victoria Blackjack")
            elif is_push:
                grant_user_xp(request, tg_id, 2, reason="Empate Blackjack")
            else:
                grant_user_xp(request, tg_id, 1, reason="Derrota Blackjack")
                
            return JsonResponse({
                'success': True,
                'game_over': True,
                'player_hand': player_hand,
                'dealer_hand': dealer_hand,
                'player_score': p_score,
                'dealer_score': d_score,
                'won': won,
                'is_push': is_push,
                'payout': payout,
                'nuevo_saldo': wallet.balance,
                'patron_vault': wallet.patron_vault,
                'message': msg
            })
            
        return JsonResponse({'success': False, 'error': 'Acción inválida'}, status=400)
        
    return render(request, 'economy/blackjack.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
    })


# ==============================================================================
# 🏪 BAZAR REAL & BOUTIQUE DE OBJETOS
# ==============================================================================
BAZAR_ITEMS = [
    # 🛡️ PROTECCIÓN Y DEFENSA
    {
        'code': 'shield_1d',
        'name': 'Escudo Sagrado (1 Día)',
        'description': 'Protege tus aposentos e inventario contra hurtos y asedios durante 24 horas continuas.',
        'icon': '🛡️',
        'price': 150,
        'category': 'defense',
        'badge': 'Seguridad',
    },
    {
        'code': 'shield_3d',
        'name': 'Baluarte Imperial (3 Días)',
        'description': 'Inviolabilidad total por 72 horas avalada por la Guardia de la Corona.',
        'icon': '🏰',
        'price': 380,
        'category': 'defense',
        'badge': 'Recomendado',
    },
    
    # 👑 ESTATUS Y NOBLEZA
    {
        'code': 'custom_title',
        'name': 'Bula de Título Personalizado',
        'description': 'Permite inscribir tu propio apodo o título honorífico en la Corte Imperial.',
        'icon': '📜',
        'price': 600,
        'category': 'status',
        'badge': 'Distinción',
    },
    {
        'code': 'vip_badge',
        'name': 'Insignia de Mecenas Dorado',
        'description': 'Destaca tu perfil con el laurel dorado perpetuo del Reino del Placer.',
        'icon': '⚜️',
        'price': 1200,
        'category': 'status',
        'badge': 'Exclusivo',
    },
    {
        'code': 'avatar_frame',
        'name': 'Marco de Oro y Diamantes',
        'description': 'Enmarca tu avatar con orfebrería imperial de alto rango nobiliario.',
        'icon': '🖼️',
        'price': 850,
        'category': 'status',
        'badge': 'Estético',
    },

    # 🌹 TRIBUTOS PARA IDOLS
    {
        'code': 'tribute_roses',
        'name': 'Ramo de Rosas Negras',
        'description': 'Ofrenda aromática que eleva la devoción y lealtad de tu Idol preferida.',
        'icon': '🌹',
        'price': 75,
        'category': 'tributes',
        'badge': 'Devoción',
    },
    {
        'code': 'tribute_champagne',
        'name': 'Champán de la Reserva Imperial',
        'description': 'Brindis de alta alcurnia para compartir en privado con una concubina.',
        'icon': '🍾',
        'price': 220,
        'category': 'tributes',
        'badge': 'Lujoso',
    },
    {
        'code': 'tribute_silk',
        'name': 'Lencería de Seda Púrpura',
        'description': 'Prenda delicada tejida con hilos de oro para tu cortesana favorita.',
        'icon': '👘',
        'price': 500,
        'category': 'tributes',
        'badge': 'Sensual',
    },
    
    # 🎲 FORTUNA Y PRIVILEGIOS
    {
        'code': 'lucky_key',
        'name': 'Llave Maestra del Casino',
        'description': 'Asegura un giro con multiplicador duplicado en la Ruleta Imperial.',
        'icon': '🗝️',
        'price': 300,
        'category': 'fortune',
        'badge': 'Ventaja',
    },
]

def bazar_shop(request):
    tg_id = get_safe_tg_id(request)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    # Inventario actual del usuario
    inventory_items = UserInventoryItem.objects.filter(telegram_user_id=tg_id)
    inv_dict = {item.item_code: item.quantity for item in inventory_items}
    
    # Coleccionables con Foto disponibles en la Boutique
    collectibles = BazarCollectible.objects.filter(is_active=True).order_by('-created_at')
    user_collectibles = UserCollectible.objects.filter(telegram_user_id=tg_id).select_related('item')

    is_staff = check_is_staff_or_admin(tg_id)

    return render(request, 'economy/bazar.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'items': BAZAR_ITEMS,
        'inventory': inv_dict,
        'collectibles': collectibles,
        'user_collectibles': user_collectibles,
        'is_staff': is_staff,
    })


def bazar_buy_action(request):
    if request.method != 'POST':
        return redirect('/economy/bazar/')
        
    tg_id = get_safe_tg_id(request)
    item_code = request.POST.get('item_code')
    
    matched_item = next((item for item in BAZAR_ITEMS if item['code'] == item_code), None)
    if not matched_item:
        messages.error(request, "El artículo solicitado no existe en los estantes del Bazar.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    
    price = matched_item['price']
    if wallet.balance < price:
        messages.error(request, f"Oro insuficiente. Requiere {price} 🪙 para adquirir {matched_item['name']}.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    with transaction.atomic():
        wallet.remove_funds(price)
        inv_item, _ = UserInventoryItem.objects.get_or_create(
            telegram_user_id=tg_id,
            item_code=item_code
        )
        inv_item.quantity += 1
        inv_item.save()
        
        # Efectos inmediatos especiales
        if item_code in ['shield_1d', 'shield_3d']:
            days = 1 if item_code == 'shield_1d' else 3
            now = timezone.now()
            # Si ya tiene un escudo activo, se suma al tiempo restante
            if profile.shield_expires_at and profile.shield_expires_at > now:
                profile.shield_expires_at += timedelta(days=days)
            else:
                profile.shield_expires_at = now + timedelta(days=days)
            profile.save(update_fields=['shield_expires_at'])
            
        elif item_code == 'vip_badge':
            profile.has_vip_badge = True
            profile.save(update_fields=['has_vip_badge'])
            
        elif item_code == 'avatar_frame':
            profile.avatar_frame = 'gold_frame'
            profile.save(update_fields=['avatar_frame'])
            
        elif item_code == 'custom_title':
            new_title = request.POST.get('custom_title_text', '').strip()
            if new_title:
                profile.custom_title = new_title[:30]
                profile.save(update_fields=['custom_title'])
                
        grant_user_xp(request, tg_id, max(5, price // 20), reason=f"Compra en Bazar: {matched_item['name']}")

    messages.success(request, f"🛍️ ¡Has adquirido con éxito '{matched_item['name']}' por {price} 🪙!")
    return redirect(f'/economy/bazar/?tg_id={tg_id}')


# ==============================================================================
# 🪔 LABORES DE LA CORTE (EQUILIBRADAS, PICARONAS Y CON DISTINCIÓN DE ROL)
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
        'title': 'Susurros de Alcoba',
        'description': 'Endulzar los oídos de nobles con confesiones atrevidas a cambio de pesados tributos.',
        'duration_minutes': 30,
        'gold_reward': 145,
        'reward_gold': 145,
        'xp_reward': 75,
        'reward_xp': 75,
        'min_level': 1,
        'icon': 'fa-solid fa-kiss-wink-heart',
        'emoji': '💋',
        'badge_color': 'bg-pink-900/60 text-pink-300 border-pink-700/50',
    },
    {
        'id': 'idol_belly_dance',
        'key': 'idol_belly_dance',
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
    """Vista principal para consultar y reclamar Labores de la Corte con distinción de roles."""
    tg_id = get_safe_tg_id(request)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    
    wallet = None
    if tg_id:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    # Identificar rol (Noble vs Idol)
    # CORREGIDO: En UserRole el campo es 'telegram_id', NO 'telegram_user_id'
    role_obj = UserRole.objects.filter(telegram_id=tg_id).first() if tg_id else None
    is_idol = (
        (role_obj and role_obj.role == 'idol')
        or (tg_id and IdolProfile.objects.filter(telegram_user_id=tg_id).exists())
    ) if tg_id else False

    user_role_type = 'idol' if is_idol else 'cliente'

    role_jobs = [j for j in JOBS_CATALOG if j['role_type'] == user_role_type]
    other_jobs = [j for j in JOBS_CATALOG if j['role_type'] != user_role_type]

    active_job = None
    is_completed = False
    time_remaining_seconds = 0

    if tg_id:
        active_job = CourtJob.objects.filter(
            telegram_user_id=tg_id,
            is_claimed=False
        ).order_by('-created_at').first()

        if active_job:
            now = timezone.now()
            if now >= active_job.finishes_at:
                is_completed = True
                time_remaining_seconds = 0
            else:
                is_completed = False
                time_remaining_seconds = max(0, int((active_job.finishes_at - now).total_seconds()))

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


@require_POST
def start_court_job(request):
    """Inicia una nueva labor de la corte si no hay otra en curso."""
    tg_id = get_safe_tg_id(request)
    if not tg_id:
        messages.error(request, 'Sesión no válida.')
        return redirect('economy:jobs')

    job_key = request.POST.get('job_key') or request.POST.get('job_id')
    
    existing = CourtJob.objects.filter(
        telegram_user_id=tg_id,
        is_claimed=False
    ).first()

    if existing:
        messages.warning(request, 'Ya tienes una labor en curso en la corte.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    matched = next((j for j in JOBS_CATALOG if j['id'] == job_key or j['key'] == job_key), None)
    if not matched:
        messages.error(request, 'La labor seleccionada no existe.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
    user_level = profile.level if profile and hasattr(profile, 'level') else 1

    if user_level < matched.get('min_level', 1):
        messages.error(request, f"Requiere nivel {matched['min_level']} en la corte.")
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    finishes = timezone.now() + timedelta(minutes=matched['duration_minutes'])
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
    return redirect(f'/economy/jobs/?tg_id={tg_id}')


@require_POST
def claim_court_job(request):
    """Reclama la recompensa de una labor completada acreditando a Wallet y UserProfile."""
    tg_id = get_safe_tg_id(request)
    if not tg_id:
        messages.error(request, 'Sesión no válida.')
        return redirect('economy:jobs')

    job = CourtJob.objects.filter(
        telegram_user_id=tg_id,
        is_claimed=False
    ).order_by('-created_at').first()

    if not job:
        messages.warning(request, 'No tienes ninguna labor para reclamar.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    if timezone.now() < job.finishes_at:
        messages.error(request, 'Esta labor aún no ha finalizado.')
        return redirect(f'/economy/jobs/?tg_id={tg_id}')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    # 🪙 1. Acreditación de Oro
    wallet.add_funds(job.gold_reward)

    # ✨ 2. Acreditación de XP
    try:
        grant_user_xp(request, tg_id, job.xp_reward, reason=f"Labor de la Corte: {job.title}")
    except Exception:
        profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
        if profile and hasattr(profile, 'xp'):
            profile.xp += job.xp_reward
            profile.save()

    # 3. Marcar como cobrada
    job.is_claimed = True
    job.save(update_fields=['is_claimed'])

    messages.success(request, f'✨ ¡Tributo reclamado! +{job.gold_reward} Oro acreditados a tu Bóveda y +{job.xp_reward} EXP.')
    return redirect(f'/economy/jobs/?tg_id={tg_id}')

# Alias de compatibilidad total
start_court_job_action = start_court_job
claim_court_job_action = claim_court_job


# ==============================================================================
# 🏺 BOUTIQUE REAL: COLECCIONABLES CON FOTOS REALES
# ==============================================================================
def buy_collectible_action(request, item_id):
    if request.method != 'POST':
        return redirect('/economy/bazar/')
        
    tg_id = get_safe_tg_id(request)
    item = get_object_or_404(BazarCollectible, id=item_id, is_active=True)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    
    if item.stock <= 0:
        messages.error(request, f"¡Agotado! Las existencias de '{item.name}' se han agotado en el reino.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    if wallet.balance < item.price:
        messages.error(request, f"Oro insuficiente. '{item.name}' cuesta {item.price} 🪙 y dispones de {wallet.balance} 🪙.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    with transaction.atomic():
        wallet.remove_funds(item.price)
        item.stock -= 1
        item.save()
        
        user_col, created = UserCollectible.objects.get_or_create(
            telegram_user_id=tg_id,
            item=item
        )
        if not created:
            user_col.quantity += 1
            user_col.save()
            
        grant_user_xp(request, tg_id, max(10, item.price // 15), reason=f"Adquisición de {item.name}")
        
    messages.success(request, f"✨ ¡Adquirido! Ahora posees el coleccionable exclusivo '{item.name}'. Ha sido añadido a tus aposentos.")
    return redirect(f'/economy/bazar/?tg_id={tg_id}')


def admin_add_collectible(request):
    tg_id = get_safe_tg_id(request)
    if not check_is_staff_or_admin(tg_id):
        messages.error(request, "Acceso reservado exclusivamente a la Corona y Administradores.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', 'relic')
        idol_name = request.POST.get('idol_name', '').strip()
        description = request.POST.get('description', '').strip()
        price = int(request.POST.get('price', 100))
        stock = int(request.POST.get('stock', 10))
        image_file = request.FILES.get('image')
        
        if not name or not image_file:
            messages.error(request, "El nombre y la fotografía del coleccionable son obligatorios.")
            return redirect(f'/economy/bazar/?tg_id={tg_id}')
            
        optimized_img = optimize_uploaded_image(image_file, max_size=(1080, 1080), quality=88)
        
        BazarCollectible.objects.create(
            name=name,
            category=category,
            idol_name=idol_name,
            description=description,
            price=price,
            stock=stock,
            image=optimized_img,
            is_active=True
        )
        messages.success(request, f"🏺 ¡Coleccionable '{name}' añadido con éxito a la Boutique Imperial!")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    return redirect(f'/economy/bazar/?tg_id={tg_id}')


def admin_delete_collectible(request, item_id):
    tg_id = get_safe_tg_id(request)
    if not check_is_staff_or_admin(tg_id):
        messages.error(request, "Acceso reservado a la Corona.")
        return redirect(f'/economy/bazar/?tg_id={tg_id}')
        
    item = get_object_or_404(BazarCollectible, id=item_id)
    name = item.name
    item.delete()
    messages.info(request, f"Coleccionable '{name}' retirado de la exhibición.")
    return redirect(f'/economy/bazar/?tg_id={tg_id}')


# ==============================================================================
# 🎫 RASCA Y GANA CLANDESTINO (SCRATCH CARDS 3x3)
# ==============================================================================
SCRATCH_TIERS = {
    'bronze': {
        'name': 'Cartón de Bronce',
        'cost': 25,
        'badge': '🥉',
        'min_level': 1,
        'card_pool': ['common'],
    },
    'silver': {
        'name': 'Cartón de Plata',
        'cost': 60,
        'badge': '🥈',
        'min_level': 3,
        'card_pool': ['rare'],
    },
    'gold': {
        'name': 'Cartón Imperial de Oro',
        'cost': 150,
        'badge': '🥇',
        'min_level': 5,
        'card_pool': ['rare', 'epic', 'legendary'],
    },
}

# ⚖️ Símbolos con Pesos Probabilísticos Calibrados (RTP ~91%)
SCRATCH_SYMBOLS = {
    'fleur': {'symbol': '⚜️', 'name': 'Flor de Lis', 'mult': 1.0, 'weight': 40, 'color': '#c084fc'},     # Recupera costo
    'wine': {'symbol': '🍷', 'name': 'Copa de Vino', 'mult': 1.5, 'weight': 28, 'color': '#f43f5e'},      # Ganancia moderada
    'gold_sack': {'symbol': '🪙', 'name': 'Saco de Oro', 'mult': 3.0, 'weight': 16, 'color': '#f59e0b'},  # Buen premio
    'diamond': {'symbol': '💎', 'name': 'Diamante Real', 'mult': 6.0, 'weight': 8, 'color': '#60a5fa'},   # Premio mayor
    'crown': {'symbol': '👑', 'name': 'Corona Imperial', 'mult': 15.0, 'weight': 3, 'color': '#fbbf24'},  # Gran Jackpot
    'photocard': {'symbol': '🎴', 'name': 'Photocard Secreta', 'mult': 1.0, 'weight': 3, 'color': '#e879f9'}, # Muy exclusiva
}

def scratch_card_view(request):
    """Muestra la interfaz del Rasca y Gana Clandestino."""
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

    cfg = SCRATCH_TIERS[tier_key]
    cost = cfg['cost']

    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(telegram_user_id=tg_id)
            profile, _ = UserProfile.objects.select_for_update().get_or_create(telegram_user_id=tg_id)

            if profile.level < cfg['min_level']:
                return JsonResponse({
                    'success': False,
                    'error': f"Requiere Nivel {cfg['min_level']} o superior para raspar este cartón."
                }, status=400)

            if wallet.balance < cost:
                return JsonResponse({
                    'success': False,
                    'error': f"Oro insuficiente. Este cartón cuesta {cost} 🪙."
                }, status=400)

            # Descontar costo y abonar al Cofre del Mecenas (8%)
            wallet.balance -= cost
            wallet.accumulate_patron_vault(cost)
            wallet.save()
            balance_after_cost = wallet.balance

            # 🍀 SISTEMA DE PITY (Suerte Dinámica Anti-Rachas Negativas)
            consecutive_losses = request.session.get("scratch_consecutive_losses", 0)
            # Base 35% de probabilidad de victoria + 10% por cada derrota consecutiva (techo en 75%)
            win_chance = min(0.75, 0.35 + (consecutive_losses * 0.10))
            is_win = random.random() < win_chance

            if is_win:
                request.session["scratch_consecutive_losses"] = 0
            else:
                request.session["scratch_consecutive_losses"] = consecutive_losses + 1

            symbols_keys = list(SCRATCH_SYMBOLS.keys())
            weights = [SCRATCH_SYMBOLS[k]["weight"] for k in symbols_keys]
            winning_key = None
            grid = []
            payout = 0
            photocard_won_data = None

            if is_win:
                winning_key = random.choices(symbols_keys, weights=weights, k=1)[0]
                mult = SCRATCH_SYMBOLS[winning_key]["mult"]
                payout = int(round(cost * mult))

                # Otorgar Photocard real verificando existencia
                if winning_key == "photocard":
                    from idols.models import Photocard, UserPhotocard
                    
                    # Probabilidad noble de rarezas según tier
                    target_rarity = "common"
                    if tier_key == "bronze":
                        target_rarity = "common"
                    elif tier_key == "silver":
                        target_rarity = random.choices(["rare", "epic"], weights=[90, 10], k=1)[0]
                    elif tier_key == "gold":
                        # Solo 2% de probabilidad de legendaria en Oro Real
                        target_rarity = random.choices(["rare", "epic", "legendary"], weights=[80, 18, 2], k=1)[0]

                    available_cards = list(Photocard.objects.filter(rarity=target_rarity).exclude(image=""))
                    
                    # Fallback si no hay cartas de esa rareza
                    if not available_cards:
                        available_cards = list(Photocard.objects.exclude(image=""))

                    if available_cards:
                        awarded_card = random.choice(available_cards)
                        UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=awarded_card)
                        photocard_won_data = {
                            "name": awarded_card.name,
                            "idol": awarded_card.display_idol_name,
                            "rarity": awarded_card.get_rarity_display(),
                            "image": awarded_card.image.url if awarded_card.image else "",
                            "color": awarded_card.get_color_hex(),
                        }

                        if awarded_card.rarity == "legendary":
                            from django.conf import settings
                            group_id = getattr(settings, "TELEGRAM_GROUP_ID", None)
                            if group_id:
                                user_name = profile.username or f"Noble_{tg_id}"
                                tier_display_name = cfg.get("name", "Cartón Imperial")
                                send_telegram_msg(
                                    chat_id=group_id,
                                    text=(
                                        f"👑 <b>¡PHOTOCARD LEGENDARIA DESENTERRADA!</b>\n\n"
                                        f"El noble <b>{user_name}</b> raspó el <i>{tier_display_name}</i> y reveló a <b>{awarded_card.name}</b> ({awarded_card.display_idol_name}) ✨"
                                    ),
                                    button_text="🎰 Ir a Rasca y Gana",
                                    button_url="https://t.me/KingdomPleasure_bot?start=entrar"
                                )

                # 💎 GENERACIÓN SEGURA DE CASILLAS GANADORAS
                # Exactamente 3 símbolos ganadores. Los 6 señuelos restantes NUNCA superan 2 copias de ninguno.
                win_indices = set(random.sample(range(9), 3))
                decoy_pool = [k for k in symbols_keys if k != winning_key]
                chosen_sample = random.sample(decoy_pool, min(3, len(decoy_pool)))
                decoy_list = (chosen_sample * 2)[:6]
                random.shuffle(decoy_list)

                decoy_i = 0
                for i in range(9):
                    if i in win_indices:
                        s_data = SCRATCH_SYMBOLS[winning_key]
                        grid.append({
                            "key": winning_key,
                            "symbol": s_data["symbol"],
                            "name": s_data["name"],
                            "color": s_data["color"],
                            "is_winner": True
                        })
                    else:
                        d_key = decoy_list[decoy_i]
                        decoy_i += 1
                        s_data = SCRATCH_SYMBOLS[d_key]
                        grid.append({
                            "key": d_key,
                            "symbol": s_data["symbol"],
                            "name": s_data["name"],
                            "color": s_data["color"],
                            "is_winner": False
                        })

                wallet.balance += payout
                wallet.save()
                grant_user_xp(request, tg_id, random.randint(2, 4), reason="Rasca y Gana Clandestino")

            else:
                # 🎭 GENERAR CUASI-VICTORIA ("Near-Miss") MATEMÁTICAMENTE IMPERMEABLE:
                # 3 pares de símbolos (3 * 2 = 6 casillas) + 3 símbolos individuales (3 * 1 = 3 casillas) = 9 casillas.
                # NINGÚN símbolo puede tener 3 copias jamás (0% riesgo de falsas victorias).
                pair_keys = random.sample(symbols_keys, 3)
                single_pool = [k for k in symbols_keys if k not in pair_keys]
                single_keys = random.sample(single_pool, 3)
                loss_keys = (pair_keys * 2) + single_keys
                random.shuffle(loss_keys)

                for k in loss_keys:
                    s_data = SCRATCH_SYMBOLS[k]
                    grid.append({
                        "key": k,
                        "symbol": s_data["symbol"],
                        "name": s_data["name"],
                        "color": s_data["color"],
                        "is_winner": False
                    })

                grant_user_xp(request, tg_id, 1, reason="Rasca y Gana Clandestino")

            serial_num = f"KOP-{random.randint(10000, 99999)}"

            return JsonResponse({
                'success': True,
                'is_win': is_win,
                'winning_symbol': SCRATCH_SYMBOLS[winning_key]['name'] if winning_key else None,
                'payout': payout,
                'photocard_won': photocard_won_data,
                'grid': grid,
                'balance_after_cost': balance_after_cost,
                'new_balance': wallet.balance,
                'patron_vault': wallet.patron_vault,
                'serial': serial_num,
                'tier_name': cfg['name'],
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f"Error en la casa de juego: {str(e)}"}, status=500)