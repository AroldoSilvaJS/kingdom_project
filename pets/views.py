from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Pet
from economy.models import Wallet

def resolve_tg_id(request):
    """Garantiza que siempre tengamos el ID real o el de prueba (123456789)"""
    raw_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
    
    if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null']:
        try:
            val = int(raw_id)
            request.session['tg_id'] = val
            return val
        except ValueError:
            pass
            
    # Si estamos probando en navegador y no hay Telegram, usamos el ID estándar de desarrollo
    fallback_id = 123456789
    request.session['tg_id'] = fallback_id
    return fallback_id

def pet_sanctuary(request):
    tg_id = resolve_tg_id(request)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()

    return render(request, 'pets/sanctuary.html', {
        'tg_id': tg_id,
        'pet': pet
    })

def adopt_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        name = request.POST.get('name', '').strip()
        species = request.POST.get('species')
        
        if name and species:
            if not Pet.objects.filter(telegram_user_id=tg_id).exists():
                Pet.objects.create(
                    telegram_user_id=tg_id,
                    name=name,
                    species=species
                )
                messages.success(request, f"¡Has adoptado a {name}! Bienvenido a tu Santuario.")
                
        return redirect(f'/pets/?tg_id={tg_id}')

def interact_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        action = request.POST.get('action')
        pet = get_object_or_404(Pet, telegram_user_id=tg_id)
        
        if action == 'feed':
            wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
            if wallet.remove_funds(10):
                pet.feed()
                messages.success(request, f"🍖 ¡Alimentaste a {pet.name}! (+25 Energía, +30 XP) (-10 🪙). Saldo restante en Bóveda: {wallet.balance} 🪙")
            else:
                messages.error(request, f"No tienes suficiente oro (10 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
                
        elif action == 'pet':
            pet.pet_action()
            messages.success(request, f"✨ ¡Acariciaste a {pet.name}! Se siente feliz y amado (+10 XP)")
            
        return redirect(f'/pets/?tg_id={tg_id}')

def change_pet(request):
    if request.method == 'POST':
        tg_id = resolve_tg_id(request)
        new_species = request.POST.get('new_species')
        new_name = request.POST.get('new_name', '').strip()
        cost = 250
        
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
            pet.save()
            messages.success(request, f"✨ ¡Ritual completado! Has transmutado tu mascota a {new_name} por {cost} 🪙. Saldo restante: {wallet.balance} 🪙")
        else:
            messages.error(request, f"No tienes suficiente oro ({cost} 🪙). Tu saldo actual es de {wallet.balance} 🪙.")
            
    return redirect(f'/pets/?tg_id={tg_id}')