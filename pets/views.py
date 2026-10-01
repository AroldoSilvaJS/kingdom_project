import random
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Pet
from economy.models import Wallet
from core.utils import grant_user_xp

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
                grant_user_xp(request, tg_id, 35, reason="Adopción de Mascota")
                messages.success(request, f"¡Has adoptado a {name}! (+35 EXP). Bienvenido a tu Santuario.")
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
        
        # 1. ACCIÓN ALIMENTAR (Validando que no esté lleno)
        if action == 'feed':
            if pet.energy >= 100:
                messages.info(request, f"🍖 {pet.name} está lleno y saciado (100% de energía). Envíalo a explorar antes de alimentarlo otra vez.")
                return redirect(f'/pets/?tg_id={tg_id}')

            wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
            if wallet.remove_funds(15):
                pet.feed()
                grant_user_xp(request, tg_id, 10, reason="Alimentar Mascota")
                messages.success(request, f"🍖 ¡Alimentaste a {pet.name}! (+25 Energía, +10 Vínculo, +20 XP Mascota) (-15 🪙).")
            else:
                messages.error(request, f"No tienes suficientes monedas (15 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
                
        # 2. ACCIÓN ACARICIAR (Con Cooldown de 30 minutos)
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
    """Envía a la mascota a explorar en busca de oro (gasta energía y tiene cooldown)"""
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        pet = get_object_or_404(Pet, telegram_user_id=tg_id)
        
        if pet.energy < 25:
            messages.error(request, f"⚠️ {pet.name} no tiene suficiente energía ({pet.energy}%). Necesita al menos 25% para explorar.")
            return redirect(f'/pets/?tg_id={tg_id}')

        if not pet.can_go_expedition():
            minutos = pet.minutes_until_next_expedition()
            messages.info(request, f"⏳ {pet.name} aún está exhausto de su último viaje. Podrá salir de expedición en {minutos} minutos.")
            return redirect(f'/pets/?tg_id={tg_id}')

        # Gastar energía
        pet.energy = max(0, pet.energy - 25)
        pet.last_expedition = timezone.now()

        # Botín aleatorio de oro según el nivel de la mascota
        gold_found = random.randint(15, 30) + (pet.level * 2)
        xp_mascota = 35
        
        pet.xp += xp_mascota
        if pet.xp >= pet.xp_to_next_level:
            pet.xp -= pet.xp_to_next_level
            pet.level += 1
            messages.success(request, f"🎉 ¡{pet.name} subió al Nivel {pet.level}!")

        pet.save()

        # Entregar botín al jugador
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        wallet.add_funds(gold_found)
        grant_user_xp(request, tg_id, 15, reason="Expedición de Mascota")

        messages.success(request, f"🌲 ¡{pet.name} regresó de los bosques con un tesoro de +{gold_found} 🪙 y +{xp_mascota} XP! (-25% Energía)")
        return redirect(f'/pets/?tg_id={tg_id}')

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
            grant_user_xp(request, tg_id, 50, reason="Ritual de Transmutación")
            messages.success(request, f"✨ ¡Ritual completado! Has transmutado tu mascota a {new_name} por {cost} 🪙.")
        else:
            messages.error(request, f"No tienes suficiente oro ({cost} 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
            
    return redirect(f'/pets/?tg_id={tg_id}')