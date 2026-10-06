import random
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from .models import Pet
from economy.models import Wallet
from core.utils import grant_user_xp
from idols.models import Photocard, UserPhotocard


def resolve_tg_id(request):
    raw_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
    if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null']:
        try:
            val = int(raw_id)
            request.session['tg_id'] = val
            return val
        except ValueError:
            pass
    fallback_id = 123456789
    request.session['tg_id'] = fallback_id
    return fallback_id


def pet_sanctuary(request):
    tg_id = resolve_tg_id(request)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    return render(request, 'pets/sanctuary.html', {'tg_id': tg_id, 'pet': pet})


def adopt_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        name = request.POST.get('name', '').strip()
        species = request.POST.get('species') or request.POST.get('new_species')
        
        if name and species:
            if not Pet.objects.filter(telegram_user_id=tg_id).exists():
                Pet.objects.create(telegram_user_id=tg_id, name=name, species=species)
                grant_user_xp(request, tg_id, 25, reason="Adopción de Mascota")
                messages.success(request, f"¡Has adoptado a {name}! (+25 EXP). Bienvenido a tu Santuario.")
            else:
                messages.info(request, "Ya tienes un compañero leal en tu Santuario.")
        else:
            messages.error(request, "Debes ingresar un nombre y elegir una especie válida.")
                
        return redirect(f'/pets/?tg_id={tg_id}')
    return redirect('/pets/')


def interact_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        action = request.POST.get('action')
        pet = get_object_or_404(Pet, telegram_user_id=tg_id)
        
        # 1. ACCIÓN ALIMENTAR
        if action == 'feed':
            if pet.energy >= 100:
                messages.info(request, f"🍖 {pet.name} está lleno y saciado (100% de energía). Envíalo a explorar antes de alimentarlo otra vez.")
                return redirect(f'/pets/?tg_id={tg_id}')

            wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
            if wallet.remove_funds(15):
                pet.feed()
                grant_user_xp(request, tg_id, 8, reason="Alimentar Mascota")
                messages.success(request, f"🍖 ¡Alimentaste a {pet.name}! (+25 Energía, +10 Vínculo, +20 XP Mascota) (-15 🪙).")
            else:
                messages.error(request, f"No tienes suficientes monedas (15 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
                
        # 2. ACCIÓN ACARICIAR
        elif action == 'pet':
            if not pet.can_be_petted():
                minutos = pet.minutes_until_next_pet()
                messages.info(request, f"💤 {pet.name} está descansando plácidamente. Podrás acariciarlo en {minutos} minutos.")
                return redirect(f'/pets/?tg_id={tg_id}')

            pet.pet_action()
            grant_user_xp(request, tg_id, 5, reason="Acariciar Mascota")
            messages.success(request, f"💖 ¡Acariciaste a {pet.name}! (+20 Vínculo, +15 XP Mascota, +5 EXP Jugador).")
            
        return redirect(f'/pets/?tg_id={tg_id}')


def expedition_pet(request):
    """Envía a la mascota a explorar una de las 3 zonas con probabilidad de Photocards reales"""
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        pet = get_object_or_404(Pet, telegram_user_id=tg_id)
        zone = request.POST.get('zone', 'forest')

        # Configuración por zona
        ZONES = {
            'forest': {'name': 'Bosque de Jade', 'min_lvl': 1, 'energy': 15, 'cooldown': 15, 'icon': '🌲'},
            'crypts': {'name': 'Criptas Olvidadas', 'min_lvl': 2, 'energy': 25, 'cooldown': 45, 'icon': '🏛️'},
            'cavern': {'name': 'Caverna de Cristal', 'min_lvl': 4, 'energy': 40, 'cooldown': 90, 'icon': '💎'},
        }

        z_data = ZONES.get(zone, ZONES['forest'])

        # Validar nivel
        if pet.level < z_data['min_lvl']:
            err = f"⚠️ {pet.name} necesita ser Nivel {z_data['min_lvl']} para entrar a {z_data['name']}."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/pets/?tg_id={tg_id}')

        # Validar energía
        if pet.energy < z_data['energy']:
            err = f"⚠️ {pet.name} no tiene suficiente energía ({pet.energy}%). Necesita al menos {z_data['energy']}%."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/pets/?tg_id={tg_id}')

        # Validar cooldown (si es zorro, 20% más rápido)
        cooldown_min = z_data['cooldown']
        if pet.species == 'fox':
            cooldown_min = int(cooldown_min * 0.8)

        if pet.last_expedition:
            tiempo_pasado = timezone.now() - pet.last_expedition
            if tiempo_pasado < timedelta(minutes=cooldown_min):
                restante = int((timedelta(minutes=cooldown_min) - tiempo_pasado).total_seconds() // 60)
                err = f"⏳ {pet.name} aún está descansando. Podrá explorar en {max(1, restante)} minutos."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.info(request, err)
                return redirect(f'/pets/?tg_id={tg_id}')

        # Consumo de energía y registro
        pet.energy = max(0, pet.energy - z_data['energy'])
        pet.last_expedition = timezone.now()

        # Cálculo de Botín
        food_found = False
        card_dropped = None

        if zone == 'forest':
            gold_found = random.randint(15, 35) + pet.level
            xp_mascota = 25
            if random.random() < 0.30:
                food_found = True
                pet.energy = min(100, pet.energy + 20)

        elif zone == 'crypts':
            gold_found = random.randint(45, 85) + (pet.level * 2)
            xp_mascota = 50
            if random.random() < 0.20:
                food_found = True
                pet.energy = min(100, pet.energy + 20)

            # 15% de probabilidad de hallar Photocard Común o Rara
            if random.random() < 0.15:
                pool = Photocard.objects.filter(rarity__in=['common', 'rare'])
                if pool.exists():
                    c = random.choice(pool)
                    UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=c)
                    card_dropped = {
                        'name': c.name,
                        'idol_name': c.display_idol_name,
                        'rarity_display': c.get_rarity_display(),
                        'color': c.get_color_hex(),
                        'image_url': c.image.url if c.image else ''
                    }

        else: # cavern
            gold_found = random.randint(100, 200) + (pet.level * 3)
            xp_mascota = 85

            # 25% de probabilidad de hallar Photocard Épica o Legendaria
            if random.random() < 0.25:
                pool = Photocard.objects.filter(rarity__in=['epic', 'legendary'])
                if not pool.exists():
                    pool = Photocard.objects.all()
                if pool.exists():
                    c = random.choice(pool)
                    UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=c)
                    card_dropped = {
                        'name': c.name,
                        'idol_name': c.display_idol_name,
                        'rarity_display': c.get_rarity_display(),
                        'color': c.get_color_hex(),
                        'image_url': c.image.url if c.image else ''
                    }

        # Subida de nivel de mascota
        leveled_up = False
        pet.xp += xp_mascota
        if pet.xp >= pet.xp_to_next_level:
            pet.xp -= pet.xp_to_next_level
            pet.level += 1
            leveled_up = True

        pet.save()

        # Entrega de oro y EXP al jugador
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        wallet.add_funds(gold_found)
        grant_user_xp(request, tg_id, max(10, gold_found // 4), reason=f"Expedición {z_data['name']}")

        if is_ajax:
            return JsonResponse({
                'success': True,
                'zone_name': z_data['name'],
                'gold': gold_found,
                'xp': xp_mascota,
                'food_found': food_found,
                'card_dropped': card_dropped,
                'leveled_up': leveled_up,
                'pet_level': pet.level,
                'pet_energy': pet.energy,
                'nuevo_saldo': wallet.balance
            })

        messages.success(request, f"¡{pet.name} exploró {z_data['name']} y volvió con +{gold_found} 🪙 y +{xp_mascota} XP!")
        return redirect(f'/pets/?tg_id={tg_id}')

    return redirect('/pets/')


def change_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        new_species = request.POST.get('new_species') or request.POST.get('species')
        new_name = request.POST.get('new_name', '').strip()
        cost = 300
        
        pet = get_object_or_404(Pet, telegram_user_id=tg_id)
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if not new_name:
            messages.error(request, "Debes ingresar un nombre para tu nueva mascota.")
            return redirect(f'/pets/?tg_id={tg_id}')
            
        if wallet.remove_funds(cost):
            pet.species = new_species
            pet.name = new_name
            pet.level = 1
            pet.xp = 0
            pet.energy = 100
            pet.happiness = 100
            pet.save()
            grant_user_xp(request, tg_id, 30, reason="Ritual de Transmutación")
            messages.success(request, f"✨ ¡Ritual completado! Has transmutado tu mascota a {new_name} por {cost} 🪙.")
        else:
            messages.error(request, f"No tienes suficiente oro ({cost} 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
            
    return redirect(f'/pets/?tg_id={tg_id}')