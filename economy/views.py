import random
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from .models import Wallet
from core.models import UserProfile
from core.utils import grant_user_xp
from pets.models import Pet
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
                        ganancia = int(apuesta * 14)
                    else:
                        ganancia = int(apuesta * 2.0)
                    
                    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                    if pet and pet.species == 'panther':
                        ganancia = int(ganancia * 1.10)
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "win"
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta

                grant_user_xp(request, tg_id, max(3, apuesta // 3), reason="Ruleta Imperial")

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
            
            grant_user_xp(request, tg_id, 45, reason="Ruleta de la Fortuna")
            messages.success(request, f"🎡 ¡La Ruleta de la Fortuna te ha otorgado +{bonus_amount} 🪙 de oro y +45 EXP!")
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
    SIMBOLOS = ['👑', '💎', '⭐', '🍇', '🍒', '🪙']
        
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
                if pet and pet.species == 'raven' and random.random() < 0.10:
                    reels = ['👑', '👑', '👑']
                else:
                    reels = [random.choice(SIMBOLOS) for _ in range(3)]
                
                if reels[0] == reels[1] == reels[2]:
                    multiplicador = 15 if reels[0] == '👑' else (10 if reels[0] == '💎' else 6)
                    ganancia = apuesta * multiplicador
                    
                    if pet and pet.species == 'panther':
                        ganancia = int(ganancia * 1.10)
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "jackpot"
                elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
                    ganancia = int(apuesta * 1.4)
                    if pet and pet.species == 'panther':
                        ganancia = int(ganancia * 1.10)
                        
                    wallet.add_funds(ganancia - apuesta)
                    resultado = "pair"
                else:
                    wallet.remove_funds(apuesta)
                    resultado = "lose"
                    ganancia = apuesta

                xp_gain = max(2, apuesta // 4)
                if resultado == "jackpot":
                    xp_gain += 25
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
                    
                    if p_val == 21:
                        ganancia = int(apuesta * 2.5)
                        pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                        if pet and pet.species == 'panther':
                            ganancia = int(ganancia * 1.10)
                            
                        wallet.add_funds(ganancia)
                        resultado = 'blackjack'
                        session_bj = None
                        grant_user_xp(request, tg_id, 20, reason="Blackjack Natural")
                    else:
                        session_bj = {
                            'bet': apuesta,
                            'player_hand': player_hand,
                            'dealer_hand': dealer_hand,
                            'finished': False
                        }
                        grant_user_xp(request, tg_id, max(2, apuesta // 5))
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
                request.session['blackjack_state'] = None
            else:
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
                pet = Pet.objects.filter(telegram_user_id=tg_id).first()
                if pet and pet.species == 'panther':
                    ganancia = int(ganancia * 1.10)
                    
                wallet.add_funds(ganancia)
                resultado = 'win'
                grant_user_xp(request, tg_id, 12, reason="Victoria Blackjack")
            elif p_val == d_val:
                wallet.add_funds(apuesta)
                resultado = 'push'
                ganancia = apuesta
            else:
                resultado = 'lose'
                ganancia = apuesta
                
            session_bj['finished'] = True
            request.session['blackjack_state'] = None

        if is_ajax:
            p_cards = session_bj['player_hand'] if session_bj else []
            d_cards = session_bj['dealer_hand'] if session_bj else []
            in_game = session_bj is not None and not session_bj.get('finished', False)

            dealer_visible = d_cards
            dealer_score_visible = calculate_hand_value(d_cards) if d_cards else 0
            if in_game and len(d_cards) >= 2:
                dealer_visible = [d_cards[0], {'val': '?', 'suit': '👑', 'is_red': False, 'hidden': True}]
                dealer_score_visible = calculate_hand_value([d_cards[0]])

            return JsonResponse({
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
            })
            
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